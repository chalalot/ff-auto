"""
Normalized Runs/Posts Storage Adapter
Implements a normalized two-table structure for storing campaign runs and posts
"""

import time
from typing import Optional, List, Dict, Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .engine import session_scope
from .models import Post, Run


def _run_dict(row: Run) -> Dict[str, Any]:
    return {
        "id": row.id,
        "persona_name": row.persona_name,
        "trend_text": row.trend_text,
        "num_posts": row.num_posts,
        "adapted_idea": row.adapted_idea,
        "trend_profile": row.trend_profile,
        "metadata": row.metadata_,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _post_dict(row: Post) -> Dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "post_index": row.post_index,
        "caption": row.caption,
        "hashtags": row.hashtags,
        "cta": row.cta,
        "image_url": row.image_url,
        "image_prompt": row.image_prompt,
        "positive_prompt": row.positive_prompt,
        "negative_prompt": row.negative_prompt,
        "visual_plan": row.visual_plan,
        "content_seed": row.content_seed,
        "metadata": row.metadata_,
        "versions": row.versions,
        "current_version": row.current_version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class RunsPostsStorage:
    """
    Normalized storage adapter using runs and posts tables.

    Schema:
    - runs: Stores high-level campaign/session data
    - posts: Stores individual post content with GCS image links
    """

    def __init__(self):
        """Initialize storage. The shared SQLAlchemy engine resolves the URL
        via DATABASE_URL (backend.database.db_utils); Alembic owns the schema.
        """
        pass

    def create_tables(self):
        """Legacy no-op: Alembic owns the schema (see backend/database/alembic)."""
        pass

    def save_run(
        self,
        run_id: str,
        trend_text: str,
        persona_name: str,
        num_posts: int,
        metadata: Optional[Dict] = None,
        adapted_idea: Optional[Dict] = None,
        trend_profile: Optional[Dict] = None
    ) -> str:
        """
        Save a new run to the database (upsert on id).

        Returns:
            The run_id
        """
        now = int(time.time())
        with session_scope() as session:
            stmt = pg_insert(Run).values(
                id=run_id,
                persona_name=persona_name,
                trend_text=trend_text,
                num_posts=num_posts,
                adapted_idea=adapted_idea,
                trend_profile=trend_profile,
                metadata_=metadata,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[Run.id],
                set_={
                    "persona_name": stmt.excluded.persona_name,
                    "trend_text": stmt.excluded.trend_text,
                    "num_posts": stmt.excluded.num_posts,
                    "adapted_idea": stmt.excluded.adapted_idea,
                    "trend_profile": stmt.excluded.trend_profile,
                    "metadata": stmt.excluded.metadata,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            session.execute(stmt)
        return run_id

    def save_post(
        self,
        post_id: str,
        run_id: str,
        post_index: int,
        caption: str,
        hashtags: List[str],
        image_url: Optional[str] = None,
        image_prompt: Optional[str] = None,
        cta: Optional[str] = None,
        positive_prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        visual_plan: Optional[Dict] = None,
        content_seed: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Save a post to the database (upsert on id).

        Returns:
            The post_id
        """
        now = int(time.time())
        with session_scope() as session:
            stmt = pg_insert(Post).values(
                id=post_id,
                run_id=run_id,
                post_index=post_index,
                caption=caption,
                hashtags=hashtags,
                cta=cta,
                image_url=image_url,
                image_prompt=image_prompt,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                visual_plan=visual_plan,
                content_seed=content_seed,
                metadata_=metadata,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[Post.id],
                set_={
                    "post_index": stmt.excluded.post_index,
                    "caption": stmt.excluded.caption,
                    "hashtags": stmt.excluded.hashtags,
                    "cta": stmt.excluded.cta,
                    "image_url": stmt.excluded.image_url,
                    "image_prompt": stmt.excluded.image_prompt,
                    "positive_prompt": stmt.excluded.positive_prompt,
                    "negative_prompt": stmt.excluded.negative_prompt,
                    "visual_plan": stmt.excluded.visual_plan,
                    "content_seed": stmt.excluded.content_seed,
                    "metadata": stmt.excluded.metadata,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            session.execute(stmt)
        return post_id

    def update_post_image_link(self, post_id: str, image_url: str):
        """
        Update the image URL for a specific post.

        Args:
            post_id: Post identifier
            image_url: Public image URL (GCS or HTTP)
        """
        with session_scope() as session:
            session.execute(
                update(Post)
                .where(Post.id == post_id)
                .values(image_url=image_url, updated_at=int(time.time()))
            )

    def save_post_version(
        self,
        post_id: str,
        visual_plan: Optional[Dict] = None,
        image_prompt: Optional[str] = None,
        positive_prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        image_url: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Save a new version of an existing post.

        Returns:
            Dict with version information
        """
        now = int(time.time())
        with session_scope() as session:
            post = session.get(Post, post_id)
            if post is None:
                raise ValueError(f"Post {post_id} not found")

            current_versions = list(post.versions or [])
            next_version = len(current_versions) + 1

            new_version = {
                "version": next_version,
                "created_at": now,
                "visual_plan": visual_plan,
                "image_prompt": image_prompt,
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "image_url": image_url,
                "metadata": metadata or {},
                "is_current": True,
            }

            for version in current_versions:
                version["is_current"] = False

            post.versions = current_versions + [new_version]
            post.current_version = next_version
            post.image_url = image_url
            post.visual_plan = visual_plan
            post.image_prompt = image_prompt
            post.positive_prompt = positive_prompt
            post.negative_prompt = negative_prompt
            post.updated_at = now

        return {
            "version": next_version,
            "created_at": now,
            "image_url": image_url,
            "is_current": True,
        }

    def get_post_versions(self, post_id: str) -> List[Dict]:
        """
        Get all versions of a post.

        Returns:
            List of version dicts
        """
        with session_scope() as session:
            post = session.get(Post, post_id)
            if post is None:
                return []
            versions = list(post.versions or [])
            current_version = post.current_version or 1

        for version in versions:
            version["is_current"] = version.get("version") == current_version

        return sorted(versions, key=lambda x: x.get("version", 0))

    def set_current_version(self, post_id: str, version_number: int) -> bool:
        """
        Set which version is the current/active one.

        Returns:
            True if successful, False otherwise
        """
        with session_scope() as session:
            post = session.get(Post, post_id)
            if post is None:
                return False

            versions = list(post.versions or [])

            target_version_data = None
            for version in versions:
                if version.get("version") == version_number:
                    version["is_current"] = True
                    target_version_data = version
                else:
                    version["is_current"] = False

            if not target_version_data:
                return False

            post.versions = versions
            post.current_version = version_number
            post.image_url = target_version_data.get("image_url")
            post.visual_plan = target_version_data.get("visual_plan")
            post.image_prompt = target_version_data.get("image_prompt")
            post.positive_prompt = target_version_data.get("positive_prompt")
            post.negative_prompt = target_version_data.get("negative_prompt")
            post.updated_at = int(time.time())
            # Force JSONB rewrite: in-place dict edits are not change-tracked.
            from sqlalchemy.orm import attributes

            attributes.flag_modified(post, "versions")
            return True

    def get_post_by_id(self, post_id: str) -> Optional[Dict]:
        """
        Get a post by its ID.

        Returns:
            Post data dict or None
        """
        with session_scope() as session:
            post = session.get(Post, post_id)
            return _post_dict(post) if post else None

    def get_run(self, run_id: str) -> Optional[Dict]:
        """
        Get a run by ID.

        Returns:
            Run data dict or None
        """
        with session_scope() as session:
            run = session.get(Run, run_id)
            return _run_dict(run) if run else None

    def get_posts_by_run(self, run_id: str) -> List[Dict]:
        """
        Get all posts for a specific run.

        Returns:
            List of post dicts
        """
        with session_scope() as session:
            rows = session.execute(
                select(Post)
                .where(Post.run_id == run_id)
                .order_by(Post.created_at.asc(), Post.post_index.asc())
            ).scalars().all()
            return [_post_dict(row) for row in rows]

    def get_run_with_posts(self, run_id: str) -> Optional[Dict]:
        """
        Get a run with all its posts.

        Returns:
            Dict with run data and posts list
        """
        run = self.get_run(run_id)
        if not run:
            return None

        run['posts'] = self.get_posts_by_run(run_id)
        return run

    def list_runs(self, limit: int = 100) -> List[Dict]:
        """
        List all runs, newest first, each with its post_count.

        Returns:
            List of run dicts
        """
        with session_scope() as session:
            rows = session.execute(
                select(Run, func.count(Post.id).label("post_count"))
                .outerjoin(Post, Post.run_id == Run.id)
                .group_by(Run.id)
                .order_by(Run.created_at.desc())
                .limit(limit)
            ).all()
            result = []
            for run, post_count in rows:
                data = _run_dict(run)
                data["post_count"] = post_count
                result.append(data)
            return result

    def get_all_runs(self, limit: int = 100) -> List[Dict]:
        """
        Get all runs with their basic information.
        Alias for list_runs() for backward compatibility.

        Returns:
            List of run dicts with keys: run_id (alias for id), trend_text,
            persona_name, num_posts, created_at, metadata
        """
        runs = self.list_runs(limit)
        # Add run_id alias for backward compatibility
        for run in runs:
            if 'id' in run:
                run['run_id'] = run['id']
        return runs

    def delete_run(self, run_id: str):
        """Delete a run and all its posts (CASCADE)."""
        with session_scope() as session:
            session.execute(delete(Run).where(Run.id == run_id))


# Singleton instance
_runs_posts_storage = None


def get_runs_posts_storage() -> RunsPostsStorage:
    """Get singleton instance of RunsPostsStorage."""
    global _runs_posts_storage

    if _runs_posts_storage is None:
        _runs_posts_storage = RunsPostsStorage()

    return _runs_posts_storage
