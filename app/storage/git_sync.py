import subprocess
from pathlib import Path
from app.config import settings
from app.core.logger import logger


class GitSync:
    """Automated Git commit & push service for output files."""

    @classmethod
    def sync_output_files(
        cls,
        message: str = settings.GIT_COMMIT_MESSAGE,
        remote: str = settings.GIT_REMOTE,
        branch: str = settings.GIT_BRANCH,
    ) -> bool:
        if not settings.AUTO_GIT_COMMIT:
            logger.debug("AUTO_GIT_COMMIT is disabled, skipping git sync.")
            return False

        try:
            # Check if git repository exists
            subprocess.run(["git", "status"], check=True, capture_output=True, text=True)

            # Add output files
            output_pattern = str(settings.OUTPUT_DIR / "*")
            subprocess.run(["git", "add", output_pattern], check=True, capture_output=True, text=True)

            # Check if there are staged changes
            diff_proc = subprocess.run(
                ["git", "diff", "--staged", "--quiet"],
                capture_output=True
            )
            if diff_proc.returncode == 0:
                logger.info("No changes to commit in output directory.")
                return True

            # Commit
            commit_proc = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True
            )
            if commit_proc.returncode != 0:
                logger.warning(f"Git commit output: {commit_proc.stderr}")

            # Push
            push_proc = subprocess.run(
                ["git", "push", remote, branch],
                capture_output=True,
                text=True
            )
            if push_proc.returncode == 0:
                logger.info(f"Successfully pushed updated node lists to {remote}/{branch}")
                return True
            else:
                logger.warning(f"Git push warning: {push_proc.stderr.strip() or push_proc.stdout.strip()}")
                return False

        except FileNotFoundError:
            logger.warning("Git executable not found on system PATH.")
            return False
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git sync command failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during git sync: {e}")
            return False
