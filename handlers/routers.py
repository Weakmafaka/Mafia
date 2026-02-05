from aiogram import Router
from handlers.common import router as common_router
from handlers.categories.support import router as support_router

from handlers.subscription.subscription import router as subscription_router
from handlers.subscription.gift_subscription import router as gift_subscription_router
from handlers.subscription.require_subscription import router as require_subscription

from handlers.categories.useful import router as useful_router
from handlers.categories.cartoons import router as cartoons_router
from handlers.categories.music import router as music_router
from handlers.categories.fairy_tales import router as fairy_tales_router
from handlers.categories.games import router as games_router
from handlers.categories.ai_assistant import router as ai_assistant_router
from handlers.categories.english import router as english
from handlers.categories.audio_book import router as audio_book

from handlers.admin_panel.admin_notify import router as admin_notify
from handlers.admin_panel.admin_stat import router as admin_stat
from handlers.admin_panel.admin_categories import router as admin_categories
from handlers.admin_panel.admin_panel import router as admin_panel
from handlers.admin_panel.gift_subscription import router as admin_gift_subscription

def setup_routers(dp):
    """Регистрирует все роутеры в диспетчере"""
    
    # Создаем главный роутер
    main_router = Router()
    
    # Включаем роутеры в главный роутер
    main_router.include_router(require_subscription)
    main_router.include_router(audio_book)
    main_router.include_router(admin_panel)
    main_router.include_router(admin_categories)
    main_router.include_router(admin_stat)
    main_router.include_router(admin_notify)
    main_router.include_router(admin_gift_subscription)
    main_router.include_router(common_router)
    main_router.include_router(support_router)
    main_router.include_router(subscription_router)
    main_router.include_router(gift_subscription_router)
    main_router.include_router(useful_router)
    main_router.include_router(cartoons_router)
    main_router.include_router(music_router)
    main_router.include_router(fairy_tales_router)
    main_router.include_router(games_router)
    main_router.include_router(ai_assistant_router)
    main_router.include_router(english)

    
    # Включаем главный роутер в диспетчер
    dp.include_router(main_router)
    
    return dp 