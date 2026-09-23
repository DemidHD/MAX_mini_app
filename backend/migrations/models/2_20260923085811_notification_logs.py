from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "notification_logs" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "event_type" VARCHAR(50) NOT NULL,
    "entity_id" BIGINT NOT NULL,
    "status" VARCHAR(20) NOT NULL,
    "attempts" INT NOT NULL,
    "error" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "user_id" BIGINT NOT NULL REFERENCES "users" ("user_id") ON DELETE CASCADE,
    CONSTRAINT "uid_notificatio_event_t_2359fd" UNIQUE ("event_type", "entity_id", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_notificatio_event_t_535c61" ON "notification_logs" ("event_type");
CREATE INDEX IF NOT EXISTS "idx_notificatio_user_id_a388bf" ON "notification_logs" ("user_id");
COMMENT ON COLUMN "notification_logs"."event_type" IS 'APPLICATION_CREATED: application_created\nCANDIDATE_INVITED: candidate_invited\nMUTUAL_INTEREST: mutual_interest\nINTERVIEW_SLOT_AVAILABLE: interview_slot_available\nINTERVIEW_BOOKED: interview_booked';
COMMENT ON COLUMN "notification_logs"."status" IS 'PENDING: pending\nSENT: sent\nFAILED: failed';
COMMENT ON TABLE "notification_logs" IS 'Одно уведомление одного типа по одной сущности одному получателю.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "notification_logs";"""


MODELS_STATE = (
    "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"
)
