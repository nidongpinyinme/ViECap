import datetime
import os
import json
import clip
import torch
import pickle
import argparse
from tqdm import tqdm
from PIL import Image
from typing import List
from ClipCap import ClipCaptionModel
from transformers import AutoTokenizer
from utils import compose_discrete_prompts
from load_annotations import load_entities_text
from search import greedy_search, beam_search, opt_search
from retrieval_categories import (
    clip_texts_embeddings,
    image_text_simiarlity,
    top_k_categories,
)


def validation_nocaps(
    args,
    inpath: str,  # path of annotations file
    entities_text: List[str],  # entities texts of vocabulary
    texts_embeddings: torch.Tensor,  # entities embeddings of vocabulary
    model: ClipCaptionModel,  # trained language model
    tokenizer: AutoTokenizer,  # tokenizer
    preprocess: clip = None,  # processor of the image
    encoder: clip = None,  # clip backbone
) -> None:

    device = args.device
    if args.using_image_features:
        with open(inpath, "rb") as infile:
            annotations = pickle.load(
                infile
            )  # [[image_path, image_split, image_features, [caption1, captions2, ...]], ...]
    else:
        with open(inpath, "r") as infile:
            annotations = json.load(
                infile
            )  # [{'split': 'near_domain', 'image_id': '4499.jpg', 'caption': [caption1, caption2, ...]}, ...]

    indomain = []
    neardomain = []
    outdomain = []
    overall = []
    for idx, annotation in tqdm(enumerate(annotations)):
        if args.using_image_features:
            image_id, split, image_features, captions = annotation
            image_features = image_features.float().unsqueeze(dim=0).to(device)
        else:
            image_id = annotation["image_id"]
            split = annotation["split"]
            captions = annotation["caption"]
            image_path = args.image_folder + split + "/" + image_id
            image = preprocess(Image.open(image_path)).unsqueeze(dim=0).to(device)
            image_features = encoder.encode_image(image).float()

        image_features /= image_features.norm(2, dim=-1, keepdim=True)
        continuous_embeddings = model.mapping_network(image_features).view(
            -1, args.continuous_prompt_length, model.gpt_hidden_size
        )
        if args.using_hard_prompt:
            logits = image_text_simiarlity(
                texts_embeddings,
                temperature=args.temperature,
                images_features=image_features,
            )
            detected_objects, _ = top_k_categories(
                entities_text, logits, args.top_k, args.threshold
            )  # List[List[]], [[category1, category2, ...], [], ...]
            detected_objects = detected_objects[
                0
            ]  # infering single image -> List[category1, category2, ...]
            discrete_tokens = (
                compose_discrete_prompts(tokenizer, detected_objects)
                .unsqueeze(dim=0)
                .to(args.device)
            )

            discrete_embeddings = model.word_embed(discrete_tokens)
            if args.only_hard_prompt:
                embeddings = discrete_embeddings
            elif args.soft_prompt_first:
                embeddings = torch.cat(
                    (continuous_embeddings, discrete_embeddings), dim=1
                )
            else:
                embeddings = torch.cat(
                    (discrete_embeddings, continuous_embeddings), dim=1
                )
        else:
            embeddings = continuous_embeddings

        if "gpt" in args.language_model:
            if not args.using_greedy_search:
                sentence = beam_search(
                    embeddings=embeddings,
                    tokenizer=tokenizer,
                    beam_width=args.beam_width,
                    model=model.gpt,
                )  # List[str]
                sentence = sentence[0]  # selected top 1
            else:
                sentence = greedy_search(
                    embeddings=embeddings, tokenizer=tokenizer, model=model.gpt
                )
        else:
            sentence = opt_search(
                prompts=args.text_prompt,
                embeddings=embeddings,
                tokenizer=tokenizer,
                beam_width=args.beam_width,
                model=model.gpt,
            )
            sentence = sentence[0]

        predict = {}
        predict["split"] = split
        predict["image_name"] = image_id
        predict["captions"] = captions
        predict["prediction"] = sentence
        overall.append(predict)
        if split == "in_domain":
            indomain.append(predict)
        elif split == "near_domain":
            neardomain.append(predict)
        elif split == "out_domain":
            outdomain.append(predict)
    out_path = args.out_path if args.out_path else args.weight_path
    with open(os.path.join(out_path, f"overall.json"), "w") as outfile:
        json.dump(overall, outfile, indent=4)
    with open(os.path.join(out_path, f"indomain.json"), "w") as outfile:
        json.dump(indomain, outfile, indent=4)
    with open(os.path.join(out_path, f"neardomain.json"), "w") as outfile:
        json.dump(neardomain, outfile, indent=4)
    with open(os.path.join(out_path, f"outdomain.json"), "w") as outfile:
        json.dump(outdomain, outfile, indent=4)


def validation_coco_flickr30k(
    args,
    inpath: str,  # path of annotations file
    entities_text: List[str],  # entities texts of vocabulary
    texts_embeddings: torch.Tensor,  # entities embeddings of vocabulary
    model: ClipCaptionModel,  # trained language model
    tokenizer: AutoTokenizer,  # tokenizer
    preprocess: clip = None,  # processor of the image
    encoder: clip = None,  # clip backbone
    tag: int = 0,
) -> None:

    device = args.device
    if args.using_image_features:
        with open(inpath, "rb") as infile:
            annotations = pickle.load(
                infile
            )  # [[image_path, image_features, [caption1, caption2, ...]], ...]
    else:
        with open(inpath, "r") as infile:
            annotations = json.load(infile)  # {image_path: [caption1, caption2, ...]}

    if args.debug:
        annotations = annotations[:500]
    predicts = []
    for idx, item in tqdm(enumerate(annotations)):
        if args.using_image_features:
            image_id, image_features, captions = item
            image_features = (
                image_features.float().unsqueeze(dim=0).to(device)
            )  # (1, clip_hidden_size)
        else:
            image_id = item
            captions = annotations[item]
            image_path = args.image_folder + image_id
            image = preprocess(Image.open(image_path)).unsqueeze(dim=0).to(device)
            image_features = encoder.encode_image(image).float()

        image_features /= image_features.norm(2, dim=-1, keepdim=True)

        # 比较图像编码和相应描述使用prior采样后的相似度
        # test_caption = captions[0]
        # clip_tokens = clip.tokenize(test_caption, truncate=True).to(device)
        # priored_samlpe = model.prior.sample(
        #     clip_tokens,
        #     num_samples_per_batch=1,
        # )
        # priored_samlpe /= priored_samlpe.norm(dim=-1, keepdim=True)
        # image_features = priored_samlpe

        continuous_embeddings = model.mapping_network(image_features).view(
            -1, args.continuous_prompt_length, model.gpt_hidden_size
        )
        if args.using_hard_prompt:
            logits = image_text_simiarlity(
                texts_embeddings,
                temperature=args.temperature,
                images_features=image_features,
            )
            detected_objects, _ = top_k_categories(
                entities_text, logits, args.top_k, args.threshold
            )  # List[List[]], [[category1, category2, ...], [], ...]
            detected_objects = detected_objects[
                0
            ]  # infering single image -> List[category1, category2, ...]
            discrete_tokens = (
                compose_discrete_prompts(tokenizer, detected_objects)
                .unsqueeze(dim=0)
                .to(args.device)
            )

            discrete_embeddings = model.word_embed(discrete_tokens)
            if args.only_hard_prompt:
                embeddings = discrete_embeddings
            elif args.soft_prompt_first:
                embeddings = torch.cat(
                    (continuous_embeddings, discrete_embeddings), dim=1
                )
            else:
                embeddings = torch.cat(
                    (discrete_embeddings, continuous_embeddings), dim=1
                )
        else:
            embeddings = continuous_embeddings

        if "gpt" in args.language_model:
            if not args.using_greedy_search:
                sentence = beam_search(
                    embeddings=embeddings,
                    tokenizer=tokenizer,
                    beam_width=args.beam_width,
                    model=model.gpt,
                )  # List[str]
                sentence = sentence[0]  # selected top 1
            else:
                sentence = greedy_search(
                    embeddings=embeddings, tokenizer=tokenizer, model=model.gpt
                )
        else:
            sentence = opt_search(
                prompts=args.text_prompt,
                embeddings=embeddings,
                tokenizer=tokenizer,
                beam_width=args.beam_width,
                model=model.gpt,
            )
            sentence = sentence[0]

        predict = {}
        predict["split"] = "valid"
        predict["image_name"] = image_id
        predict["captions"] = captions
        predict["prediction"] = sentence
        predicts.append(predict)
    # print("dis_loss: ", dis_loss / len(annotations))
    # 检查路径是否存在
    out_path = args.out_path if args.out_path else args.weight_path
    if not os.path.exists(out_path):
        os.makedirs(out_path)
    out_json_path = os.path.join(out_path, f"{tag}.json")
    with open(out_json_path, "w") as outfile:
        json.dump(predicts, outfile, indent=4)


@torch.no_grad()
def main(args) -> None:
    # initializing
    device = args.device
    clip_name = args.clip_model.replace("/", "")
    # 适配L14
    clip_hidden_size = 512 if args.clip_model == "ViT-B/32" else 768
    # clip_hidden_size = 640 if "RN" in args.clip_model else 512

    # loading categories vocabulary for objects
    if args.name_of_entities_text == "visual_genome_entities":
        entities_text = load_entities_text(
            args.name_of_entities_text,
            "../../../dataset/annotations/all_objects_attributes_relationships.pickle",
            not args.disable_all_entities,
        )
        if args.prompt_ensemble:  # loading ensemble embeddings
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/visual_genome_embedding_{clip_name}_with_ensemble.pickle",
            )
        else:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/visual_genome_embedding_{clip_name}.pickle",
            )
    elif args.name_of_entities_text == "coco_entities":
        entities_text = load_entities_text(
            args.name_of_entities_text,
            "../../../dataset/annotations/coco_categories.json",
            not args.disable_all_entities,
        )
        if args.prompt_ensemble:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/coco_embeddings_{clip_name}_with_ensemble.pickle",
            )
        else:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/coco_embeddings_{clip_name}.pickle",
            )
    elif args.name_of_entities_text == "open_image_entities":
        entities_text = load_entities_text(
            args.name_of_entities_text,
            "../../../dataset/annotations/oidv7-class-descriptions-boxable.csv",
            not args.disable_all_entities,
        )
        if args.prompt_ensemble:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/open_image_embeddings_{clip_name}_with_ensemble.pickle",
            )
        else:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/open_image_embeddings_{clip_name}.pickle",
            )
    elif args.name_of_entities_text == "vinvl_vg_entities":
        entities_text = load_entities_text(
            args.name_of_entities_text,
            "../../../dataset/annotations/VG-SGG-dicts-vgoi6-clipped.json",
            not args.disable_all_entities,
        )
        if args.prompt_ensemble:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/vg_embeddings_{clip_name}_with_ensemble.pickle",
            )
        else:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/vg_embeddings_{clip_name}.pickle",
            )
    elif args.name_of_entities_text == "vinvl_vgoi_entities":
        entities_text = load_entities_text(
            args.name_of_entities_text,
            "../../../dataset/annotations/vgcocooiobjects_v1_class2ind.json",
            not args.disable_all_entities,
        )
        if args.prompt_ensemble:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/vgoi_embeddings_{clip_name}_with_ensemble.pickle",
                device=device,
                clip_type=args.clip_model,
            )
        else:
            texts_embeddings = clip_texts_embeddings(
                entities_text,
                f"../../../dataset/annotations/vgoi_embeddings_{clip_name}.pickle",
            )
    else:
        print("The entities text should be input correctly!")
        return

    # loading model
    tokenizer = AutoTokenizer.from_pretrained(args.language_model)
    model = ClipCaptionModel(
        args.continuous_prompt_length,
        args.clip_project_length,
        clip_hidden_size,
        gpt_type=args.language_model,
    )
    if args.weight_path.endswith(".pt"):
        # 直接加载指定权重文件
        weight_files = [args.weight_path]
    else:
        # 获取weight_path路径下所有pt文件
        weight_files = os.listdir(args.weight_path)
        weight_files = [
            os.path.join(args.weight_path, f)
            for f in weight_files
            if f.endswith(".pt") and not f.endswith("latest.pt")
        ]

    counter = 0
    for file in weight_files:
        model.load_state_dict(torch.load(file, map_location=device))
        # 只保留文件名
        file = file.split("/")[-1]
        model.to(device)
        if not args.using_image_features:
            encoder, preprocess = clip.load(args.clip_model, device=device)
            inpath = args.path_of_val_datasets
        else:
            inpath = (
                args.path_of_val_datasets[:-5] + f"_{clip_name}.pickle"
            )  # file with image features
        if args.name_of_datasets == "nocaps":  # nocaps
            if args.using_image_features:
                validation_nocaps(
                    args, inpath, entities_text, texts_embeddings, model, tokenizer
                )
            else:
                validation_nocaps(
                    args,
                    inpath,
                    entities_text,
                    texts_embeddings,
                    model,
                    tokenizer,
                    preprocess,
                    encoder,
                )
        else:  # coco, flickr30k
            if args.using_image_features:
                validation_coco_flickr30k(
                    args,
                    inpath,
                    entities_text,
                    texts_embeddings,
                    model,
                    tokenizer,
                    tag=args.name_of_datasets + "-" + str(counter),
                )
            else:
                validation_coco_flickr30k(
                    args,
                    inpath,
                    entities_text,
                    texts_embeddings,
                    model,
                    tokenizer,
                    preprocess,
                    encoder,
                    tag=args.name_of_datasets + "-" + str(counter),
                )
        counter += 1


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cuda:0")
    # parser.add_argument("--clip_model", default="ViT-B/32")
    parser.add_argument("--clip_model", default="ViT-L/14")
    parser.add_argument("--language_model", default="gpt2")
    parser.add_argument("--continuous_prompt_length", type=int, default=10)
    parser.add_argument("--clip_project_length", type=int, default=10)
    parser.add_argument("--temperature", type=float, default=0.01)
    parser.add_argument("--top_k", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.4)
    parser.add_argument(
        "--using_image_features",
        action="store_true",
        default=True,
        help="using pre-extracted image features",
    )
    parser.add_argument(
        "--name_of_datasets",
        default="flickr30k",
        choices=("coco", "flickr30k", "nocaps"),
    )
    parser.add_argument(
        "--path_of_val_datasets",
        default="../../../dataset/flickr30k/test_captions.json",
    )
    parser.add_argument(
        "--disable_all_entities",
        action="store_true",
        default=False,
        help="whether to use entities with a single word only",
    )
    parser.add_argument(
        "--name_of_entities_text",
        default="vinvl_vgoi_entities",
        choices=(
            "visual_genome_entities",
            "coco_entities",
            "open_image_entities",
            "vinvl_vg_entities",
            "vinvl_vgoi_entities",
        ),
    )
    parser.add_argument("--prompt_ensemble", action="store_true", default=True)
    parser.add_argument(
        "--weight_path",
        default="eval/",
    )

    now = datetime.datetime.now()
    date_time_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    parser.add_argument(
        "--image_folder", default="../../../dataset/flickr30k/flickr30k-images/"
    )
    parser.add_argument("--out_path", default="")
    parser.add_argument("--using_hard_prompt", action="store_true", default=True)
    parser.add_argument("--soft_prompt_first", action="store_true", default=True)
    parser.add_argument("--only_hard_prompt", action="store_true", default=False)
    parser.add_argument(
        "--using_greedy_search",
        action="store_true",
        default=False,
        help="greedy search or beam search",
    )
    parser.add_argument("--beam_width", type=int, default=5, help="width of beam")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--text_prompt", type=str, default=None)
    args = parser.parse_args()
    print("args: {}\n".format(vars(args)))

    main(args)
