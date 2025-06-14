import os
from pathlib import Path

# --- 配置 ---

# 1. 自动确定项目根目录
# Path(__file__).resolve() 获取此脚本的绝对路径。
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    # 如果在交互式环境（如Jupyter）中运行，__file__ 可能不存在，
    # 此时假定当前工作目录就是项目根目录。
    PROJECT_ROOT = Path.cwd()

OUTPUT_FILENAME = "full_code_text.txt"

# 2. 定义需要排除的目录和文件
# 排除这些目录，可以避免扫描不必要的生成文件、缓存和版本控制历史
EXCLUDE_DIRS = {
    '.git',                         # Git 版本控制
    '__pycache__',                  # Python 字节码缓存 (必须排除)
    'patf_trading_framework.egg-info', # Python 打包元数据 (必须排除)
    'cache',                        # 自定义的缓存目录
    'output',                       # 自定义的输出目录
    '.vscode',                      # VSCode 编辑器配置
    '.idea',                        # PyCharm 等 JetBrains IDE 配置
    'venv',                         # Python 虚拟环境
    '.venv',                        # 另一种常见的虚拟环境名称
    'env',                          # 还有一种常见的虚拟环境名称
    'build',                        # 项目构建输出目录
    'dist',                         # 项目分发包目录
    'logs',                         # 日志目录
}

# 3. 定义明确要排除的文件扩展名（二进制文件等）
# 这样可以避免尝试读取图片、数据文件等非文本内容
EXCLUDE_EXTS = {
    '.pyc', '.pyo', '.so', '.dll', '.exe',
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg',
    '.parquet', '.arrow', '.feather',
    '.zip', '.gz', '.tar', '.rar', '.7z',
    '.db', '.sqlite3',
    '.pdf', '.docx', '.xlsx',
}

# 4. 排除脚本自己生成的输出文件
EXCLUDE_FILES = {
    OUTPUT_FILENAME,
    '.DS_Store',    # macOS 系统文件
    'Thumbs.db',    # Windows 系统文件
    # 你的 .gitignore 中也提到了 full_code_text.txt，这里再次确认
    'full_code_text.txt', 
}


def is_likely_text_file(filepath: Path) -> bool:
    """
    通过扩展名和内容初步判断文件是否为文本文件。
    一个简单的启发式方法：二进制文件通常包含 NULL 字节。
    """
    if filepath.suffix.lower() in EXCLUDE_EXTS:
        return False
        
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            if b'\0' in chunk:
                return False
    except (IOError, PermissionError):
        return False
    
    return True


def combine_project_files():
    """
    递归扫描整个项目目录，将所有文本文件的内容合并到一个输出文件中。
    """
    output_filepath = PROJECT_ROOT / OUTPUT_FILENAME
    
    print(f"Project root identified as: {PROJECT_ROOT}")
    print(f"Output will be saved to: {output_filepath}\n")
    
    files_processed_count = 0
    files_skipped_count = 0

    try:
        with open(output_filepath, 'w', encoding='utf-8', errors='ignore') as outfile:
            outfile.write("Here are the full project files, structured with relative paths.\n\n")

            for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
                current_dir = Path(dirpath)
                
                dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
                
                for filename in filenames:
                    if filename in EXCLUDE_FILES:
                        continue

                    filepath = current_dir / filename
                    
                    if not is_likely_text_file(filepath):
                        relative_path_str = filepath.relative_to(PROJECT_ROOT).as_posix()
                        # print(f"  - Skipping binary/excluded file: {relative_path_str}")
                        files_skipped_count += 1
                        continue
                    
                    relative_path_str = filepath.relative_to(PROJECT_ROOT).as_posix()
                    
                    start_tag = f"<{relative_path_str}>\n"
                    end_tag = f"</{relative_path_str}>\n\n"
                    
                    print(f"  + Processing: {relative_path_str}")
                    files_processed_count += 1
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as infile:
                            content = infile.read()
                        
                        outfile.write(start_tag)
                        outfile.write(content.strip())
                        outfile.write(f"\n{end_tag}")
                        
                    except Exception as e:
                        print(f"    [ERROR] Could not read file {relative_path_str}: {e}")
                        files_skipped_count += 1

        print("\n--- Summary ---")
        print(f"Successfully processed {files_processed_count} files.")
        print(f"Skipped {files_skipped_count} binary, excluded, or unreadable files.")
        print(f"Combined output saved to: {output_filepath}")

    except IOError as e:
        print(f"\n[FATAL ERROR] Could not write to output file {output_filepath}: {e}")
    except Exception as e:
        print(f"\n[FATAL ERROR] An unexpected error occurred: {e}")


if __name__ == "__main__":
    combine_project_files()