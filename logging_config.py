"""
日志配置模块
统一管理应用的日志格式和输出
"""
import logging
import sys
from typing import Optional


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> None:
    """统一配置日志系统

    Args:
        level: 日志级别（默认 INFO）
        log_file: 可选的日志文件路径，同时输出到控制台和文件
        format_string: 可选的自定义格式字符串

    示例：
        # 基础配置（仅控制台）
        setup_logging()

        # 调试模式 + 文件输出
        setup_logging(level=logging.DEBUG, log_file='/tmp/app.log')
    """
    # 默认格式
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 创建格式化器
    formatter = logging.Formatter(format_string, datefmt='%Y-%m-%d %H:%M:%S')

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有处理器（避免重复添加）
    root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 可选的文件处理器
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
