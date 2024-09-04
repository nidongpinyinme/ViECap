source /media/luzm/data/workspace/software/miniconda3/bin/activate MacCap
WEIGHT_PATH=total_eval
TIME_START=$(date "+%Y-%m-%d-%H-%M-%S")
LOG_FILE="$WEIGHT_PATH/$TIME_START.log"
rm WEIGHT_PATH/*.json

echo "=======================COCO VAL=========================="
coco_val="python validation.py  --name_of_datasets coco --path_of_val_datasets ../../../dataset/annotations/test_captions.json --name_of_entities_text coco_entities --image_folder ../../../dataset/coco/val2014/ --using_image_features --using_hard_prompt --soft_prompt_first --weight_path $WEIGHT_PATH  | tee -a  ${LOG_FILE}"
echo $coco_val | tee -a  ${LOG_FILE}
eval $coco_val
if [ $? -ne 0 ]; then
curl -s -o /dev/null "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/coco验证失败?group=实验通知"
exit 1
fi

echo "==========================FLICKR VAL================================"

flicker_val="python validation.py --using_image_features --name_of_datasets flickr30k --path_of_val_datasets ../../../dataset/annotations/flickr30k_test_captions.json --name_of_entities_text vinvl_vgoi_entities --image_folder ../../../dataset/flickr30k/flickr30k-images/ --using_hard_prompt --soft_prompt_first --weight_path=$WEIGHT_PATH | tee -a  $LOG_FILE"
echo $flicker_val | tee -a  ${LOG_FILE}
eval $flicker_val
if [ $? -ne 0 ]; then
curl -s -o /dev/null "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/flicker验证失败?group=实验通知"
exit 1
fi
# --threshold 0.3 \
# --using_greedy_search \

echo "==========================NOCAPS VAL================================"
nocaps_val="python validation.py --using_image_features --name_of_datasets nocaps --path_of_val_datasets ../../../dataset/annotations/nocaps_corpus.json --name_of_entities_text vinvl_vgoi_entities --image_folder ../../../dataset/nocaps/val --using_hard_prompt --soft_prompt_first --weight_path=$WEIGHT_PATH | tee -a  $LOG_FILE"
echo $nocaps_val | tee -a  ${LOG_FILE}
eval $nocaps_val
if [ $? -ne 0 ]; then
curl -s -o /dev/null "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/nocaps验证失败?group=实验通知"
exit 1
fi

echo "==========================COCO EVAL================================"
coco_eval="python ../evaluation/cocoeval.py --result_file_path  ${WEIGHT_PATH} |& tee -a  ${LOG_FILE}"
echo $coco_eval | tee -a  ${LOG_FILE}
eval $coco_eval
echo $?
if [ $? -ne 0 ]; then
curl -s -o /dev/null "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/评估失败?group=实验通知"
exit 1
fi

echo "==========================Done============================="
curl -s -o /dev/null  "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/实验已完成?group=实验通知"
