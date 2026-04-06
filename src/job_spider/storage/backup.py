"""
数据库备份模块。

提供 SQLite 数据库的完整备份、恢复、清理和验证功能。
"""

import gzip
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from config.logging import get_logger

logger = get_logger(__name__)


class BackupStatus(Enum):
    """备份状态枚举。"""

    VALID = "valid"
    INVALID = "invalid"
    CORRUPTED = "corrupted"


@dataclass
class BackupInfo:
    """备份文件信息。"""

    name: str
    path: Path
    size: int
    created_at: datetime
    compressed: bool
    status: BackupStatus = BackupStatus.VALID

    @property
    def size_human(self) -> str:
        """返回人类可读的文件大小。"""
        for unit in ["B", "KB", "MB", "GB"]:
            if self.size < 1024:
                return f"{self.size:.2f} {unit}"
            self.size /= 1024
        return f"{self.size:.2f} TB"


class BackupResult(BaseModel):
    """备份操作结果。"""

    success: bool
    message: str
    backup_name: Optional[str] = None
    backup_path: Optional[str] = None
    size: Optional[int] = None


class RestoreResult(BaseModel):
    """恢复操作结果。"""

    success: bool
    message: str
    restored_from: Optional[str] = None


class DatabaseBackup:
    """
    数据库备份管理器。

    支持完整备份、恢复、清理和验证功能。
    支持压缩备份以节省存储空间。

    Example:
        >>> from config.settings import get_settings
        >>> settings = get_settings()
        >>> backup_manager = DatabaseBackup(
        ...     db_path=settings.database.sqlite_path,
        ...     backup_dir=settings.backup.backup_dir,
        ...     max_backups=settings.backup.max_backups,
        ...     compress=settings.backup.compress,
        ... )
        >>> result = backup_manager.create_backup()
        >>> print(result)
    """

    BACKUP_PREFIX = "jobs_backup_"
    BACKUP_SUFFIX_DB = ".db"
    BACKUP_SUFFIX_GZ = ".db.gz"

    def __init__(
        self,
        db_path: Path | str,
        backup_dir: Path | str,
        max_backups: int = 10,
        compress: bool = True,
    ):
        """
        初始化备份管理器。

        Args:
            db_path: 数据库文件路径
            backup_dir: 备份目录
            max_backups: 最大保留备份数量
            compress: 是否压缩备份
        """
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups
        self.compress = compress

        # 确保备份目录存在
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _generate_backup_name(self) -> str:
        """生成备份文件名。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = self.BACKUP_SUFFIX_GZ if self.compress else self.BACKUP_SUFFIX_DB
        return f"{self.BACKUP_PREFIX}{timestamp}{suffix}"

    def create_backup(self, custom_name: Optional[str] = None) -> BackupResult:
        """
        创建数据库完整备份。

        使用 SQLite 的备份 API 确保数据一致性。

        Args:
            custom_name: 自定义备份名称（可选）

        Returns:
            BackupResult: 备份结果
        """
        # 检查数据库文件是否存在
        if not self.db_path.exists():
            logger.warning("database_not_found", path=str(self.db_path))
            return BackupResult(
                success=False,
                message=f"数据库文件不存在: {self.db_path}",
            )

        try:
            # 生成备份文件名
            if custom_name:
                backup_name = custom_name
                if not backup_name.endswith(self.BACKUP_SUFFIX_DB) and not backup_name.endswith(
                    self.BACKUP_SUFFIX_GZ
                ):
                    suffix = self.BACKUP_SUFFIX_GZ if self.compress else self.BACKUP_SUFFIX_DB
                    backup_name = f"{backup_name}{suffix}"
            else:
                backup_name = self._generate_backup_name()

            backup_path = self.backup_dir / backup_name

            # 创建备份（使用 SQLite 备份 API）
            self._backup_with_sqlite_api(backup_path)

            # 获取备份文件大小
            backup_size = backup_path.stat().st_size

            logger.info(
                "backup_created",
                name=backup_name,
                size=backup_size,
                compressed=self.compress,
            )

            return BackupResult(
                success=True,
                message="备份创建成功",
                backup_name=backup_name,
                backup_path=str(backup_path),
                size=backup_size,
            )

        except Exception as e:
            logger.exception("backup_failed", error=str(e))
            return BackupResult(
                success=False,
                message=f"备份创建失败: {e}",
            )

    def _backup_with_sqlite_api(self, backup_path: Path) -> None:
        """
        使用 SQLite 备份 API 创建备份。

        确保数据一致性，支持在线备份。
        """
        # 先创建临时备份文件
        temp_path = backup_path.with_suffix(".tmp")

        try:
            # 使用 SQLite 的备份 API
            source_conn = sqlite3.connect(str(self.db_path))
            dest_conn = sqlite3.connect(str(temp_path))

            source_conn.backup(dest_conn)

            dest_conn.close()
            source_conn.close()

            # 如果需要压缩
            if self.compress:
                with open(temp_path, "rb") as f_in:
                    with gzip.open(backup_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                temp_path.unlink()
            else:
                temp_path.rename(backup_path)

        except Exception:
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()
            raise

    def list_backups(self) -> list[BackupInfo]:
        """
        列出所有备份文件。

        Returns:
            list[BackupInfo]: 备份信息列表，按时间降序排列
        """
        backups = []

        for file_path in self.backup_dir.iterdir():
            if not file_path.is_file():
                continue

            name = file_path.name
            if not name.startswith(self.BACKUP_PREFIX):
                continue

            # 解析时间戳
            try:
                timestamp_str = name.replace(self.BACKUP_PREFIX, "").replace(
                    self.BACKUP_SUFFIX_GZ, ""
                ).replace(self.BACKUP_SUFFIX_DB, "")
                created_at = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except ValueError:
                # 无法解析时间戳，使用文件修改时间
                created_at = datetime.fromtimestamp(file_path.stat().st_mtime)

            # 检查是否压缩
            compressed = name.endswith(self.BACKUP_SUFFIX_GZ)

            # 获取文件大小
            size = file_path.stat().st_size

            # 验证备份
            status = self._validate_backup_status(file_path, compressed)

            backups.append(
                BackupInfo(
                    name=name,
                    path=file_path,
                    size=size,
                    created_at=created_at,
                    compressed=compressed,
                    status=status,
                )
            )

        # 按时间降序排列
        backups.sort(key=lambda x: x.created_at, reverse=True)
        return backups

    def _validate_backup_status(self, backup_path: Path, compressed: bool) -> BackupStatus:
        """
        验证备份文件状态。

        Args:
            backup_path: 备份文件路径
            compressed: 是否压缩

        Returns:
            BackupStatus: 备份状态
        """
        try:
            # 如果是压缩文件，先解压到临时文件
            if compressed:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = Path(tmp.name)

                try:
                    with gzip.open(backup_path, "rb") as f_in:
                        with open(tmp_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    status = self._check_sqlite_integrity(tmp_path)
                finally:
                    tmp_path.unlink()
            else:
                status = self._check_sqlite_integrity(backup_path)

            return status

        except Exception as e:
            logger.warning("backup_validation_failed", path=str(backup_path), error=str(e))
            return BackupStatus.CORRUPTED

    def _check_sqlite_integrity(self, db_path: Path) -> BackupStatus:
        """
        检查 SQLite 数据库完整性。

        Args:
            db_path: 数据库文件路径

        Returns:
            BackupStatus: 备份状态
        """
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()

            if result and result[0] == "ok":
                return BackupStatus.VALID
            else:
                return BackupStatus.INVALID

        except Exception:
            return BackupStatus.CORRUPTED

    def restore_backup(self, backup_name: str) -> RestoreResult:
        """
        从备份恢复数据库。

        Args:
            backup_name: 备份文件名

        Returns:
            RestoreResult: 恢复结果
        """
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            logger.warning("backup_not_found", name=backup_name)
            return RestoreResult(
                success=False,
                message=f"备份文件不存在: {backup_name}",
            )

        try:
            # 验证备份完整性
            compressed = backup_name.endswith(self.BACKUP_SUFFIX_GZ)
            status = self._validate_backup_status(backup_path, compressed)

            if status != BackupStatus.VALID:
                logger.warning("backup_invalid", name=backup_name, status=status.value)
                return RestoreResult(
                    success=False,
                    message=f"备份文件已损坏或无效: {backup_name}",
                )

            # 创建当前数据库的备份（如果存在）
            if self.db_path.exists():
                safety_backup = self.db_path.with_suffix(".db.bak")
                shutil.copy2(self.db_path, safety_backup)
                logger.info("safety_backup_created", path=str(safety_backup))

            # 恢复数据库
            if compressed:
                with gzip.open(backup_path, "rb") as f_in:
                    with open(self.db_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(backup_path, self.db_path)

            logger.info("backup_restored", name=backup_name)

            return RestoreResult(
                success=True,
                message="数据库恢复成功",
                restored_from=backup_name,
            )

        except Exception as e:
            logger.exception("restore_failed", error=str(e))
            return RestoreResult(
                success=False,
                message=f"恢复失败: {e}",
            )

    def cleanup_old_backups(self, keep_count: Optional[int] = None) -> list[str]:
        """
        清理旧备份，只保留最近 N 个。

        Args:
            keep_count: 保留数量，默认使用配置的 max_backups

        Returns:
            list[str]: 被删除的备份文件名列表
        """
        if keep_count is None:
            keep_count = self.max_backups

        backups = self.list_backups()
        deleted = []

        # 只删除有效的备份，保留无效/损坏的备份供人工检查
        valid_backups = [b for b in backups if b.status == BackupStatus.VALID]

        if len(valid_backups) <= keep_count:
            logger.info("cleanup_skipped", reason="backups_within_limit", count=len(valid_backups))
            return deleted

        # 删除超出数量的旧备份
        to_delete = valid_backups[keep_count:]

        for backup in to_delete:
            try:
                backup.path.unlink()
                deleted.append(backup.name)
                logger.info("backup_deleted", name=backup.name)
            except Exception as e:
                logger.warning("delete_failed", name=backup.name, error=str(e))

        return deleted

    def verify_backup(self, backup_name: str) -> BackupStatus:
        """
        验证指定备份的完整性。

        Args:
            backup_name: 备份文件名

        Returns:
            BackupStatus: 备份状态
        """
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            return BackupStatus.CORRUPTED

        compressed = backup_name.endswith(self.BACKUP_SUFFIX_GZ)
        return self._validate_backup_status(backup_path, compressed)

    def get_backup_info(self, backup_name: str) -> Optional[BackupInfo]:
        """
        获取指定备份的详细信息。

        Args:
            backup_name: 备份文件名

        Returns:
            BackupInfo 或 None
        """
        backups = self.list_backups()
        for backup in backups:
            if backup.name == backup_name:
                return backup
        return None

    def get_latest_backup(self) -> Optional[BackupInfo]:
        """
        获取最新的有效备份。

        Returns:
            BackupInfo 或 None
        """
        backups = self.list_backups()
        for backup in backups:
            if backup.status == BackupStatus.VALID:
                return backup
        return None

    def get_backup_stats(self) -> dict:
        """
        获取备份统计信息。

        Returns:
            dict: 统计信息
        """
        backups = self.list_backups()

        total_size = sum(b.size for b in backups)
        valid_count = sum(1 for b in backups if b.status == BackupStatus.VALID)
        invalid_count = sum(1 for b in backups if b.status == BackupStatus.INVALID)
        corrupted_count = sum(1 for b in backups if b.status == BackupStatus.CORRUPTED)

        return {
            "total_count": len(backups),
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "corrupted_count": corrupted_count,
            "total_size": total_size,
            "total_size_human": self._format_size(total_size),
            "backup_dir": str(self.backup_dir),
            "max_backups": self.max_backups,
        }

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小。"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"
