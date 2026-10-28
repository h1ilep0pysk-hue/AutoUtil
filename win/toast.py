import logging

from winotify import Notification, audio

from core.notifier import Notice

log = logging.getLogger("autoutil.toast")

APP_ID = "AutoUtil"


def show_toast(notice: Notice) -> None:
    try:
        toast = Notification(
            app_id=APP_ID,
            title=notice.title,
            msg=notice.body,
            duration="short",
        )
        toast.set_audio(audio.Silent, loop=False)

        toast.show()
    except Exception:
        log.exception("Не удалось показать уведомление")