import asyncio
import logging
import sys
from core.config import Config
# Import skill dynamically or statically. For now, static import is fine for single skill.
from skills.usd_jpy_expert.skill import UsdJpySkill

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("glitchygopher")

async def main():
    logger.info("Starting GlitchyGopher...")
    
    # Load configuration
    config = Config.load()
    
    # Initialize Skill
    skill = UsdJpySkill(config)
    
    logger.info("Entering heartbeat loop (15 minutes)...")
    
    while True:
        try:
            logger.info("Heartbeat: Executing skills...")
            await skill.execute()
            logger.info("Skill execution execution complete.")
        except Exception as e:
            logger.error(f"Error during execution: {e}", exc_info=True)
        
        # Wait 31 minutes (Moltbook rate limit: 1 post/30m)
        await asyncio.sleep(31 * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("GlitchyGopher stopped by user.")
