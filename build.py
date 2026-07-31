import PyInstaller.__main__

PyInstaller.__main__.run([
    "desktop_app.py",
    "--name=TradeRepublicAnalyzer",
    "--onefile",
    "--windowed",
    "--noconsole",
    "--clean",
    "--icon=assets/app.ico",
    "--add-data=templates;templates",
    "--add-data=static;static",
    "--add-data=assets;assets",
    "--hidden-import=webview",
    "--hidden-import=portfolio",
    "--hidden-import=portfolio.engine",
    "--hidden-import=portfolio.parser",
    "--collect-all=webview",
    "--collect-all=flask",
    "--collect-all=pandas",
    "--collect-all=numpy",
])
