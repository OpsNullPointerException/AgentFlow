#!/bin/bash

# 项目启动脚本
# 同时启动Django服务器和Celery worker

# 确保脚本在项目根目录执行
if [ ! -f "manage.py" ]; then
    echo "错误: 请在项目根目录执行此脚本"
    exit 1
fi

# 检查依赖
if ! command -v celery &> /dev/null; then
    echo "错误: celery 命令未找到，请确保已安装 Celery"
    echo "提示: pip install celery"
    exit 1
fi

if ! python -c "import flower" &> /dev/null; then
    echo "警告: flower 命令未找到，监控界面将不可用"
    echo "提示: pip install flower"
    FLOWER_AVAILABLE=false
else
    FLOWER_AVAILABLE=true
fi

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 设置日志目录
mkdir -p logs

# 保存进程ID的文件
DJANGO_PID_FILE="logs/django.pid"
CELERY_PID_FILE="logs/celery.pid"
FLOWER_PID_FILE="logs/flower.pid"

# 检查服务状态
check_status() {
    echo -e "${YELLOW}检查服务状态...${NC}"
    
    # 检查Django服务
    if [ -f "$DJANGO_PID_FILE" ]; then
        PID=$(cat $DJANGO_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${GREEN}Django 服务运行中 (PID: $PID)${NC}"
        else
            echo -e "${RED}Django PID文件存在，但进程已停止${NC}"
            rm $DJANGO_PID_FILE
        fi
    else
        echo -e "${RED}Django 服务未运行${NC}"
    fi
    
    # 检查Celery服务
    if [ -f "$CELERY_PID_FILE" ]; then
        PID=$(cat $CELERY_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${GREEN}Celery worker 运行中 (PID: $PID)${NC}"
        else
            echo -e "${RED}Celery PID文件存在，但进程已停止${NC}"
            rm $CELERY_PID_FILE
        fi
    else
        echo -e "${RED}Celery worker 未运行${NC}"
    fi
    
    # 检查Flower服务
    if [ -f "$FLOWER_PID_FILE" ]; then
        PID=$(cat $FLOWER_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${GREEN}Flower 监控界面运行中 (PID: $PID)${NC}"
            echo -e "${GREEN}访问地址: http://localhost:5555${NC}"
        else
            echo -e "${RED}Flower PID文件存在，但进程已停止${NC}"
            rm $FLOWER_PID_FILE
        fi
    else
        echo -e "${RED}Flower 监控界面未运行${NC}"
    fi
}

# 启动服务
start_services() {
    echo -e "${YELLOW}启动服务...${NC}"
    
    # 检查Django是否已运行
    if [ -f "$DJANGO_PID_FILE" ]; then
        PID=$(cat $DJANGO_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${YELLOW}Django 服务已经在运行 (PID: $PID)${NC}"
        else
            echo -e "${YELLOW}启动 Django 服务${NC}"
            python manage.py runserver 0.0.0.0:8000 > logs/django.log 2>&1 &
            echo $! > $DJANGO_PID_FILE
            echo -e "${GREEN}Django 服务已启动 (PID: $!)${NC}"
        fi
    else
        echo -e "${YELLOW}启动 Django 服务${NC}"
        python manage.py runserver 0.0.0.0:8000 > logs/django.log 2>&1 &
        echo $! > $DJANGO_PID_FILE
        echo -e "${GREEN}Django 服务已启动 (PID: $!)${NC}"
    fi
    
    # 检查Celery是否已运行
    if [ -f "$CELERY_PID_FILE" ]; then
        PID=$(cat $CELERY_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${YELLOW}Celery worker 已经在运行 (PID: $PID)${NC}"
        else
            echo -e "${YELLOW}启动 Celery worker (使用solo池)${NC}"
            celery -A smartdocs_project worker --pool=solo -l INFO > logs/celery_console.log 2>&1 &
            echo $! > $CELERY_PID_FILE
            echo -e "${GREEN}Celery worker 已启动 (PID: $!)${NC}"
        fi
    else
        echo -e "${YELLOW}启动 Celery worker (使用solo池)${NC}"
        celery -A smartdocs_project worker --pool=solo -l INFO > logs/celery_console.log 2>&1 &
        echo $! > $CELERY_PID_FILE
        echo -e "${GREEN}Celery worker 已启动 (PID: $!)${NC}"
    fi
    
    # 启动Flower监控界面
    if [ "$FLOWER_AVAILABLE" = true ]; then
        if [ -f "$FLOWER_PID_FILE" ]; then
            PID=$(cat $FLOWER_PID_FILE)
            if ps -p $PID > /dev/null; then
                echo -e "${YELLOW}Flower 监控界面已经在运行 (PID: $PID)${NC}"
            else
                echo -e "${YELLOW}启动 Flower 监控界面${NC}"
                celery -A smartdocs_project flower > logs/flower.log 2>&1 &
                echo $! > $FLOWER_PID_FILE
                echo -e "${GREEN}Flower 监控界面已启动 (PID: $!)${NC}"
                echo -e "${GREEN}访问地址: http://localhost:5555${NC}"
            fi
        else
            echo -e "${YELLOW}启动 Flower 监控界面${NC}"
            celery -A smartdocs_project flower > logs/flower.log 2>&1 &
            echo $! > $FLOWER_PID_FILE
            echo -e "${GREEN}Flower 监控界面已启动 (PID: $!)${NC}"
            echo -e "${GREEN}访问地址: http://localhost:5555${NC}"
        fi
    else
        echo -e "${YELLOW}Flower未安装，跳过启动监控界面${NC}"
        echo -e "${YELLOW}提示: pip install flower${NC}"
    fi
    
    echo -e "${GREEN}所有服务已启动${NC}"
    echo -e "${YELLOW}Django 日志: logs/django.log${NC}"
    echo -e "${YELLOW}Celery 控制台输出: logs/celery_console.log${NC}"
    echo -e "${YELLOW}Celery 任务日志: logs/celery.log${NC}"
    if [ "$FLOWER_AVAILABLE" = true ]; then
        echo -e "${YELLOW}Flower 日志: logs/flower.log${NC}"
        echo -e "${GREEN}Flower 监控界面: http://localhost:5555${NC}"
    fi
}

# 停止服务
stop_services() {
    echo -e "${YELLOW}停止服务...${NC}"
    
    # 停止Django
    if [ -f "$DJANGO_PID_FILE" ]; then
        PID=$(cat $DJANGO_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${YELLOW}停止 Django 服务 (PID: $PID)${NC}"
            kill $PID
            sleep 2
            if ps -p $PID > /dev/null; then
                echo -e "${RED}Django 服务未能正常停止，强制终止${NC}"
                kill -9 $PID
            fi
            rm $DJANGO_PID_FILE
            echo -e "${GREEN}Django 服务已停止${NC}"
        else
            echo -e "${RED}Django 进程已不存在${NC}"
            rm $DJANGO_PID_FILE
        fi
    else
        echo -e "${RED}Django 服务未运行${NC}"
    fi
    
    # 停止Celery
    if [ -f "$CELERY_PID_FILE" ]; then
        PID=$(cat $CELERY_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${YELLOW}停止 Celery worker (PID: $PID)${NC}"
            kill $PID
            sleep 2
            if ps -p $PID > /dev/null; then
                echo -e "${RED}Celery worker 未能正常停止，强制终止${NC}"
                kill -9 $PID
            fi
            rm $CELERY_PID_FILE
            echo -e "${GREEN}Celery worker 已停止${NC}"
        else
            echo -e "${RED}Celery 进程已不存在${NC}"
            rm $CELERY_PID_FILE
        fi
    else
        echo -e "${RED}Celery worker 未运行${NC}"
    fi
    
    # 停止Flower
    if [ -f "$FLOWER_PID_FILE" ]; then
        PID=$(cat $FLOWER_PID_FILE)
        if ps -p $PID > /dev/null; then
            echo -e "${YELLOW}停止 Flower 监控界面 (PID: $PID)${NC}"
            kill $PID
            sleep 2
            if ps -p $PID > /dev/null; then
                echo -e "${RED}Flower 监控界面未能正常停止，强制终止${NC}"
                kill -9 $PID
            fi
            rm $FLOWER_PID_FILE
            echo -e "${GREEN}Flower 监控界面已停止${NC}"
        else
            echo -e "${RED}Flower 进程已不存在${NC}"
            rm $FLOWER_PID_FILE
        fi
    else
        echo -e "${RED}Flower 监控界面未运行${NC}"
    fi
    
    echo -e "${GREEN}所有服务已停止${NC}"
}

# 查看日志
view_logs() {
    if [ "$1" == "django" ]; then
        tail -f logs/django.log
    elif [ "$1" == "celery" ]; then
        tail -f logs/celery.log
    elif [ "$1" == "celery_console" ]; then
        tail -f logs/celery_console.log
    elif [ "$1" == "flower" ]; then
        tail -f logs/flower.log
    else
        echo -e "${RED}未知的日志类型: $1${NC}"
        echo -e "${YELLOW}可用选项: django, celery, celery_console, flower${NC}"
    fi
}

# 主函数
main() {
    case "$1" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            stop_services
            sleep 2
            start_services
            ;;
        status)
            check_status
            ;;
        logs)
            if [ -z "$2" ]; then
                echo -e "${RED}请指定要查看的日志类型${NC}"
                echo -e "${YELLOW}用法: $0 logs [django|celery|celery_console]${NC}"
                exit 1
            fi
            view_logs $2
            ;;
        *)
            echo -e "${YELLOW}SmartDocs 服务管理脚本${NC}"
            echo -e "${YELLOW}用法: $0 {start|stop|restart|status|logs}${NC}"
            echo -e "  start   - 启动Django和Celery服务"
            echo -e "  stop    - 停止所有服务"
            echo -e "  restart - 重启所有服务"
            echo -e "  status  - 查看服务状态"
            echo -e "  logs    - 查看日志 (django|celery|celery_console)"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"