from aiogram import Router

from handlers.game_rooms.create import router as create_router
from handlers.game_rooms.day_vote import router as day_vote_router
from handlers.game_rooms.gameplay import router as gameplay_router
from handlers.game_rooms.join import router as join_router
from handlers.game_rooms.lobby import router as lobby_router
from handlers.game_rooms.menu import router as menu_router
from handlers.game_rooms.night_mafia import router as night_mafia_router
from handlers.game_rooms.stages import router as stages_router

router = Router()
router.include_router(menu_router)
router.include_router(create_router)
router.include_router(join_router)
router.include_router(lobby_router)
router.include_router(gameplay_router)
router.include_router(night_mafia_router)
router.include_router(day_vote_router)
router.include_router(stages_router)
