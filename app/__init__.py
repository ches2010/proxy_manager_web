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

# 注意：不再尝试导入不存在的 'routes' 模块
# from . import routes  # <-- 这行已删除

# 如果 app/app.py 中的路由是直接通过 @app.route 定义的，
# 那么这些路由会在 app/app.py 中创建 'app' 实例时被关联起来。
# launch.py 通过 'app.app:app' 指向的就是这个已经配置好路由的实例。



