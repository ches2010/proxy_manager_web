# app/__init__.py
from flask import Flask

def create_app():
    app = Flask(__name__)
    # 可加载配置
    # app.config.from_json("../config/config.json")
    return app

# 供 launch.py 调用
app = create_app()
