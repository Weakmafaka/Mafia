from typing import List, Optional, Tuple


STAGE_LABELS = {
    "lover": "Любовница",
    "commissar": "Комиссар",
    "doctor": "Доктор",
    "angel": "Ангел",
    "mafia": "Мафия",
    "maniac": "Маньяк",
    "ghost": "Призраки",
    "day_vote": "Город",
}


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)


def build_first_night_message(stage: str, night_number: int) -> str:
    return (
        "Город засыпает.\n"
        "Шаги стихают, окна гаснут, и над улицами повисает тревожная тишина.\n\n"
        "Ночь {}.\n"
        "Просыпается {}.\n"
        "У этой роли есть одна минута, чтобы решить исход этой ночи."
    ).format(night_number, stage_label(stage))


def build_stage_opening_message(stage: str, night_number: int, previous_stage: Optional[str] = None) -> str:
    if stage == "day_vote":
        return (
            "Город просыпается.\n"
            "Лица бледны, голоса сдержанны, а в воздухе уже чувствуется страх и подозрение.\n\n"
            "Подозрения уже висят в воздухе.\n"
            "Пришло время назвать того, кого город готов изгнать.\n"
            "Утро закончится только тогда, когда каждый живой игрок скажет свое слово."
        )

    if previous_stage is None:
        return build_first_night_message(stage, night_number)

    return (
        "{} сделал свой выбор.\n"
        "Тишина на мгновение становится еще тяжелее.\n\n"
        "Теперь просыпается {}.\n"
        "У этой роли есть одна минута, чтобы сделать свой ход."
    ).format(stage_label(previous_stage), stage_label(stage))


def build_stage_locked_message(stage: str) -> str:
    return (
        "{} сделал свой выбор.\n"
        "Ночь не ждет и идет дальше."
    ).format(stage_label(stage))


def build_mafia_resolution_message(source: str) -> str:
    if source == "players":
        return (
            "Мафия договорилась шепотом и снова растворилась в темноте.\n"
            "Их выбор сделан."
        )
    if source == "timeout_existing_votes":
        return (
            "Время мафии вышло.\n"
            "Ночь приняла тот выбор, к которому мафия склонялась сильнее всего."
        )
    return (
        "Время мафии вышло.\n"
        "Ночь не стала ждать и сама решила, куда поведет страх."
    )


def build_night_result_message(
    killed_players: List[Tuple[int, str, str]],
    fearful_count: int = 0,
) -> str:
    if not killed_players:
        base = (
            "Город просыпается.\n"
            "Рассвет приходит тяжело, но улицы все еще отвечают шагами.\n"
            "Этой ночью никто не погиб."
        )
    else:
        players_line = ", ".join(name for _, name, _ in killed_players)
        base = (
            "Город просыпается.\n"
            "Рассвет приносит новость, от которой в груди становится холоднее.\n"
            "Этой ночью погибли: {}."
        ).format(players_line)

    if fearful_count > 0:
        fear_line = (
            "\n\nНе для всех эта ночь закончилась одинаково.\n"
            "Кто-то все еще не может избавиться от липкого чувства ужаса."
        )
        return base + fear_line
    return base


def build_day_vote_result_message(eliminated_name: Optional[str], skipped: bool, tie: bool) -> str:
    if tie:
        return (
            "Площадь гудела до последнего, но решимости так и не хватило.\n"
            "Голоса раскололись, и страх остался среди людей.\n"
            "Сегодня никто не был изгнан."
        )
    if skipped:
        return (
            "Сомнения оказались сильнее решимости.\n"
            "Город отступил в последний момент и никого не изгнал."
        )
    if eliminated_name:
        return (
            "На площади стало тихо в тот самый миг, когда решение было принято.\n"
            'Сегодня город изгнал игрока "{}".'
        ).format(eliminated_name)
    return "Дневное голосование завершено."


def build_victory_message(winner_title: str, winners_line: str) -> str:
    if winner_title == "Город":
        intro = "Над городом впервые за долгое время становится легче дышать."
    elif winner_title == "Мафия":
        intro = "Город пал. Ночь окончательно взяла верх."
    else:
        intro = "На улице больше не осталось никого, кто мог бы помешать последнему охотнику."

    return (
        "{}\n\n"
        "Игра завершена.\n"
        "Победила сторона: {}.\n"
        "Победители: {}.\n\n"
        "Победители получают +50 рейтинга.\n"
        "Проигравшие получают -50 рейтинга."
    ).format(intro, winner_title, winners_line or "-")
