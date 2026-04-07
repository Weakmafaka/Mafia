from aiogram import Router

from handlers.common import router as common_router
from handlers.game_rooms import router as game_rooms_router


def setup_routers(dp):
    main_router = Router()
    main_router.include_router(game_rooms_router)
    main_router.include_router(common_router)
    dp.include_router(main_router)
    return dp
