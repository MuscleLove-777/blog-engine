"""blog_engine - 共通ブログエンジンパッケージ

config.py + prompts.py を差し替えるだけで新しいブログを量産できる
汎用ブログ自動生成エンジン。

使い方:
    各ブログフォルダの generate_and_build.py から呼び出す:
        from blog_engine.generate_and_build import run
        import config
        import prompts
        run(config, prompts)
"""

__version__ = "1.0.0"
