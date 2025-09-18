# app/__init__.py

from flask import Flask
import os

# 获取当前文件所在目录（app/）
current_dir = os.path.dirname(os.path.abspath(__file__))

# 创建 Flask 应用，指定静态文件和模板目录
app = Flask(
    __name__,
    static_folder=os.path.join(current_dir, 'static'),      # ← 指向 app/static/
    template_folder=os.path.join(current_dir, 'templates')  # ← 指向 app/templates/
)

# 可选：开发时禁用缓存，方便调试
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# 导入路由（必须在 app 创建之后）
from . import routes
