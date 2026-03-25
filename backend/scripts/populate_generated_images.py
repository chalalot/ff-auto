import os
import asyncio
import logging
from pathlib import Path

from backend.config import GlobalConfig
from backend.third_parties.comfyui_client import ComfyUIClient
from backend.database.image_logs_storage import ImageLogsStorage

DEBUG_DB_POLLING = os.getenv("DEBUG_DB_POLLING", "false").lower() == "true"
log_level = logging.INFO if DEBUG_DB_POLLING else logging.WARNING
logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PopulateImages")


async def main():
    output_dir = Path(GlobalConfig.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    storage = ImageLogsStorage()
    client = ComfyUIClient()

    pending_items = storage.get_pending_executions()

    if not pending_items:
        if DEBUG_DB_POLLING:
            logger.info("No pending executions found in database.")
        return

    if DEBUG_DB_POLLING:
        logger.info(f"Checking {len(pending_items)} pending executions...")

    for item in pending_items:
        execution_id = item["execution_id"]
        image_ref_path = item["image_ref_path"]

        if not execution_id:
            continue

        try:
            try:
                status_data = await client.check_status(execution_id)
                status = status_data.get("status")
            except Exception as e:
                logger.error(f"Failed to check status for {execution_id}: {e}")
                continue

            if status == "completed":
                logger.info(f"✅ Execution {execution_id} completed. Processing...")

                output_images = status_data.get("output_images", [])
                comfy_image_path = None

                if output_images and isinstance(output_images, list):
                    first_output = output_images[0]
                    if isinstance(first_output, dict):
                        for key, paths in first_output.items():
                            if paths and len(paths) > 0:
                                comfy_image_path = paths[0]
                                break

                if comfy_image_path:
                    try:
                        image_bytes = await client.download_image_by_path(comfy_image_path)
                    except Exception as e:
                        logger.error(f"Failed to download image by path for {execution_id}: {e}")
                        try:
                            image_bytes = await client.download_image(execution_id)
                        except Exception as inner_e:
                            logger.error(f"Fallback download failed for {execution_id}: {inner_e}")
                            storage.mark_as_failed(execution_id)
                            continue

                    base_name = Path(image_ref_path).stem if image_ref_path else execution_id
                    result_filename = f"result_{base_name}_{execution_id}.png"
                    local_result_path = output_dir / result_filename

                    local_result_path.write_bytes(image_bytes)
                    logger.info(f"Saved local result to {local_result_path}")

                    storage.update_result_path(
                        execution_id=execution_id,
                        result_image_path=str(local_result_path),
                        new_ref_path=None,
                    )
                    logger.info(f"Database updated for {execution_id}")
                else:
                    logger.warning(f"No output image path found for {execution_id}")

            elif status == "failed":
                logger.error(f"❌ Execution {execution_id} failed. Marking as failed in DB.")
                storage.mark_as_failed(execution_id)

        except Exception as e:
            logger.error(f"Error processing {execution_id}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
