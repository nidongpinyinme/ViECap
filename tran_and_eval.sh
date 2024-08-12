source /media/luzm/data/workspace/software/miniconda3/bin/activate MacCap

SHELL_FOLDER=$(cd "$(dirname "$0")";pwd)

EXP_NAME=`echo "$(basename $0)" | cut -d'.' -f1` 

# 输出路径为test，文件夹下使用日期和时间区分不同次的训练，每个子文件夹中包括训练日志和测试结果，其中日志在根目录中，测试结果包括checkpoints和outputs两个文件夹，以及一个csv文件
TIME_START=$(date "+%Y-%m-%d-%H-%M-%S")
out_dir=test/${TIME_START}
# 如果脚本有传入参数，则日志名称为参数，否则为当前时间
if [ -n "$1" ]; then
    log_name=$1
else
    log_name=$TIME_START
fi
LOG_FILE="$out_dir/$log_name.log"
mkdir -p $out_dir

echo "=====================training============================="
echo "RUNNING EXPERIMENTS: $log_name, saving in $out_dir"

train_command="python main.py --epochs 3 --use_prior --checkpoint test/2024-08-08-15-14-42/checkpoints/coco_prefix_latest.pt --out_dir $out_dir/checkpoints/ --using_hard_prompt --soft_prompt_first --frozen_gpt| tee -a  ${LOG_FILE}"
# train_command="python main.py --epochs 3 --use_prior  --out_dir $out_dir/checkpoints/ --using_hard_prompt --soft_prompt_first --frozen_gpt| tee -a  ${LOG_FILE}"
echo $train_command
eval $train_command
echo $?
if [ $? -ne 0 ]; then
    echo "Training failed: $train_command"
    curl -s -o /dev/null "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/训练失败?group=实验通知"
    exit 1
fi

echo "=======================Validation=========================="
val_command="python validation.py  --weight_path $out_dir/checkpoints/  --using_image_features --using_hard_prompt --soft_prompt_first --out_path $out_dir/outputs | tee -a  ${LOG_FILE}"
echo $val_command
eval $val_command
echo $?
if [ $? -ne 0 ]; then
echo "Validation failed: $val_command"
curl -s -o /dev/null "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/验证失败?group=实验通知"
exit 1
fi

echo "=======================Evaluation=========================="
eva_command="python ../evaluation/cocoeval.py --result_file_path $out_dir/outputs --eval_file_name ${TIME_START}| tee -a  ${LOG_FILE}"
echo $eva_command
eval $eva_command
if [ $? -ne 0 ]; then
    echo "Evaluation failed: $eva_command"
    curl -s -o /dev/null "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/评估失败?group=实验通知"
    exit 1
fi

echo "==========================Done============================="

curl -s -o /dev/null  "https://api.day.app/iA9hqfBBTRf4RSktCuN7d4/实验已完成?group=实验通知"
