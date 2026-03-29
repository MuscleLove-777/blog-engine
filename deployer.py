"""blog_engine - GitHub Pagesデプロイモジュール

生成した静的サイトをGitHub Pagesにデプロイする。
"""
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


class GitHubPagesDeployer:
    """GitHub Pagesへのデプロイを管理するクラス"""

    def __init__(self, config):
        """デプロイ設定を初期化する

        Args:
            config: ブログ設定モジュール
        """
        self.config = config
        self.site_dir = config.SITE_DIR
        self.repo = config.GITHUB_REPO
        self.branch = getattr(config, "GITHUB_BRANCH", "gh-pages")
        self.token = getattr(config, "GITHUB_TOKEN", "")

        if not self.repo:
            raise ValueError(
                "GITHUB_REPO が設定されていません。\n"
                "環境変数 GITHUB_REPO を設定してください（例: username/repo-name）"
            )

    def deploy(self) -> dict:
        """サイトをGitHub Pagesにデプロイする"""
        logger.info("GitHub Pagesへのデプロイを開始します...")

        if not self.site_dir.exists():
            return {
                "status": "error",
                "message": "サイトディレクトリが見つかりません。先にビルドを実行してください。"
            }

        try:
            self._run_git_commands()

            username = self.repo.split("/")[0]
            repo_name = self.repo.split("/")[1]
            url = f"https://{username}.github.io/{repo_name}/"

            logger.info("デプロイ完了: %s", url)
            return {
                "status": "success",
                "message": "デプロイが完了しました",
                "url": url,
            }

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error("デプロイ中にエラー発生: %s", error_msg)
            return {
                "status": "error",
                "message": f"デプロイに失敗しました: {error_msg}",
            }
        except Exception as e:
            logger.error("予期しないエラー: %s", e)
            return {
                "status": "error",
                "message": f"予期しないエラーが発生しました: {e}",
            }

    def _run_git_commands(self):
        """gitコマンドを実行してgh-pagesブランチにpushする"""
        site_dir = str(self.site_dir)

        if self.token:
            remote_url = f"https://{self.token}@github.com/{self.repo}.git"
        else:
            remote_url = f"https://github.com/{self.repo}.git"

        def run(cmd, cwd=site_dir):
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, shell=True,
            )
            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, stderr=result.stderr
                )
            return result.stdout

        git_dir = self.site_dir / ".git"
        if not git_dir.exists():
            run("git init")
            run(f"git remote add origin {remote_url}")
            logger.info("gitリポジトリを初期化しました")
        else:
            run(f"git remote set-url origin {remote_url}")

        run(f"git checkout -B {self.branch}")
        run("git add -A")

        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run(f'git commit -m "サイト更新: {now}"')
            logger.info("変更をコミットしました")
        except subprocess.CalledProcessError:
            logger.info("変更がないためコミットをスキップします")
            return

        run(f"git push -f origin {self.branch}")
        logger.info("GitHub Pagesにプッシュしました")

    def check_status(self) -> dict:
        """現在のデプロイ状態を確認する"""
        username = self.repo.split("/")[0] if "/" in self.repo else ""
        repo_name = self.repo.split("/")[1] if "/" in self.repo else ""

        return {
            "repo": self.repo,
            "branch": self.branch,
            "site_dir": str(self.site_dir),
            "site_exists": self.site_dir.exists(),
            "url": f"https://{username}.github.io/{repo_name}/" if username else "未設定",
            "token_configured": bool(self.token),
        }
