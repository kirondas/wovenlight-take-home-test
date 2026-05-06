import sys

from wovenlight_scheduler.app import create_app
from wovenlight_scheduler.config import Config, ConfigError


def main() -> None:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    app = create_app(config)
    app.run(host=config.host, port=config.port)


if __name__ == "__main__":
    main()
