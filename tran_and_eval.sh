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

echo "python main.py --epochs 1 --out_dir $out_dir/checkpoints/ --frozen_gpt| tee -a  ${LOG_FILE}"
python main.py --epochs 1 --out_dir $out_dir/checkpoints/ --frozen_gpt| tee -a  ${LOG_FILE}

echo "=======================Validation=========================="
echo "python validation.py  --weight_path $out_dir/checkpoints/ --out_path $out_dir/outputs | tee -a  ${LOG_FILE}"
python validation.py  --weight_path $out_dir/checkpoints/  --out_path $out_dir/outputs | tee -a  ${LOG_FILE}
echo "=======================Evaluation=========================="
echo "python ../evaluation/cocoeval.py --result_file_path $out_dir/outputs | tee -a  ${LOG_FILE}"
python ../evaluation/cocoeval.py --result_file_path $out_dir/outputs | tee -a  ${LOG_FILE}    