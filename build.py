import os
import platform

import PyInstaller.__main__


def add_data(src, dst):
    return f"--add-data={src}{os.pathsep}{dst}"


args = [
    "desktop_app.py",
    "--name=Klarwert",
    "--onefile",
    "--windowed",
    "--clean",
    add_data("templates", "templates"),
    add_data("static", "static"),
    add_data("assets", "assets"),
    "--hidden-import=webview",
    "--hidden-import=portfolio",
    "--hidden-import=portfolio.engine",
    "--hidden-import=portfolio.parser",
    "--collect-all=webview",
    "--collect-all=flask",
    "--collect-all=pandas",
    "--collect-all=numpy",
]

if platform.system() == "Windows":
    args.append("--icon=assets/app.ico")

PyInstaller.__main__.run(args)
