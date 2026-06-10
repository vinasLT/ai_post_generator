from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.utils import BASE_DIR


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"

class Settings(BaseSettings):
    # Database
    DB_HOST: str = "localhost"   
    DB_PORT: str = "5432"
    DB_NAME: str = "test_db"
    DB_USER: str = "postgres"
    DB_PASS: str = "testpass"


    # Application
    APP_NAME: str = "posts-generator-service"
    DEBUG: bool = True
    ENVIRONMENT: Environment = Environment.DEVELOPMENT

    @property
    def enable_docs(self) -> bool:
        return self.ENVIRONMENT in [Environment.DEVELOPMENT]

    OPENAI_API_KEY: str = ''


    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_EXCHANGE_NAME: str = 'events'
    RABBITMQ_QUEUE_NAME: str = 'post_generator_service'

    # gRPC
    RPC_AUCTION_API_URL: str = "localhost:50052"
    RCP_CALCULATOR_URL: str = 'localhost:50051'

    model_config = SettingsConfigDict(env_file=f"{BASE_DIR}/.env")



settings = Settings()