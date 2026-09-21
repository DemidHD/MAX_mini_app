from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "users" (
    "user_id" BIGINT NOT NULL PRIMARY KEY,
    "first_name" VARCHAR(100) NOT NULL,
    "last_name" VARCHAR(100),
    "username" VARCHAR(100),
    "language_code" VARCHAR(10),
    "role" VARCHAR(20),
    "avatar_path" VARCHAR(500),
    "avatar_updated_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "last_auth_at" TIMESTAMPTZ NOT NULL
);
COMMENT ON COLUMN "users"."role" IS 'CANDIDATE: candidate\nEMPLOYER: employer';
COMMENT ON TABLE "users" IS 'Пользователь MAX Найм.';
CREATE TABLE IF NOT EXISTS "sessions" (
    "id" UUID NOT NULL PRIMARY KEY,
    "expires_at" TIMESTAMPTZ NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "last_used_at" TIMESTAMPTZ NOT NULL,
    "user_id" BIGINT NOT NULL REFERENCES "users" ("user_id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_sessions_user_id_80072d" ON "sessions" ("user_id");
COMMENT ON TABLE "sessions" IS 'Связывает cookie браузера с конкретным `users.user_id`.';
CREATE TABLE IF NOT EXISTS "candidate_profiles" (
    "desired_role" VARCHAR(255) NOT NULL,
    "city" VARCHAR(255),
    "salary" DECIMAL(12,2),
    "schedule" VARCHAR(100),
    "experience_months" INT,
    "available_from" DATE,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "user_id" BIGINT NOT NULL PRIMARY KEY REFERENCES "users" ("user_id") ON DELETE CASCADE
);
COMMENT ON TABLE "candidate_profiles" IS 'Профиль кандидата, используемый для подбора вакансий. Связь с User — 1:1.';
CREATE TABLE IF NOT EXISTS "vacancies" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL,
    "location" VARCHAR(255),
    "salary_min" DECIMAL(12,2),
    "salary_max" DECIMAL(12,2),
    "schedule" VARCHAR(100),
    "status" VARCHAR(20) NOT NULL,
    "public_token" VARCHAR(32) UNIQUE,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "employer_id" BIGINT NOT NULL REFERENCES "users" ("user_id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_vacancies_status_5bc383" ON "vacancies" ("status");
CREATE INDEX IF NOT EXISTS "idx_vacancies_employe_3ec4a6" ON "vacancies" ("employer_id");
COMMENT ON COLUMN "vacancies"."status" IS 'DRAFT: draft\nPUBLISHED: published\nCLOSED: closed';
COMMENT ON TABLE "vacancies" IS 'Вакансия работодателя.';
CREATE TABLE IF NOT EXISTS "referral_links" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "code" VARCHAR(100) NOT NULL UNIQUE,
    "created_at" TIMESTAMPTZ NOT NULL,
    "source_user_id" BIGINT NOT NULL REFERENCES "users" ("user_id") ON DELETE CASCADE,
    "vacancy_id" BIGINT NOT NULL REFERENCES "vacancies" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_referral_li_vacancy_c0191e" ON "referral_links" ("vacancy_id");
COMMENT ON TABLE "referral_links" IS 'Ссылка для привлечения кандидатов на вакансию. Функционал P2.';
CREATE TABLE IF NOT EXISTS "screening_questions" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "question" TEXT NOT NULL,
    "type" VARCHAR(50) NOT NULL,
    "required" BOOL NOT NULL,
    "sort_order" INT NOT NULL,
    "validation_rules" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "vacancy_id" BIGINT NOT NULL REFERENCES "vacancies" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_screening_q_vacancy_711702" ON "screening_questions" ("vacancy_id");
COMMENT ON COLUMN "screening_questions"."type" IS 'TEXT: text\nNUMBER: number\nBOOLEAN: boolean\nCHOICE: choice';
COMMENT ON TABLE "screening_questions" IS 'Вопрос первичного отбора. В P0 на вакансию приходится 3–4 вопроса.';
CREATE TABLE IF NOT EXISTS "vacancy_criteria" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "type" VARCHAR(50) NOT NULL,
    "required" BOOL NOT NULL,
    "value" JSONB NOT NULL,
    "weight" DECIMAL(5,2),
    "created_at" TIMESTAMPTZ NOT NULL,
    "vacancy_id" BIGINT NOT NULL REFERENCES "vacancies" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_vacancy_cri_vacancy_0a07a9" ON "vacancy_criteria" ("vacancy_id");
COMMENT ON COLUMN "vacancy_criteria"."type" IS 'LOCATION: location\nSCHEDULE: schedule\nSALARY: salary\nAVAILABLE_FROM: available_from\nEXPERIENCE: experience\nCERTIFICATE: certificate';
COMMENT ON TABLE "vacancy_criteria" IS 'Формализованный критерий вакансии для hard filters и ranking.';
CREATE TABLE IF NOT EXISTS "applications" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(50) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "candidate_id" BIGINT NOT NULL REFERENCES "users" ("user_id") ON DELETE CASCADE,
    "vacancy_id" BIGINT NOT NULL REFERENCES "vacancies" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_application_vacancy_4a8093" UNIQUE ("vacancy_id", "candidate_id")
);
CREATE INDEX IF NOT EXISTS "idx_application_status_594257" ON "applications" ("status");
CREATE INDEX IF NOT EXISTS "idx_application_vacancy_25d332" ON "applications" ("vacancy_id");
CREATE INDEX IF NOT EXISTS "idx_application_candida_63890d" ON "applications" ("candidate_id");
COMMENT ON COLUMN "applications"."status" IS 'CREATED: created\nSCREENING: screening\nHARD_FILTER_FAILED: hard_filter_failed\nPASSED: passed\nUNDER_REVIEW: under_review\nREJECTED: rejected\nINVITED: invited\nMUTUAL_INTEREST: mutual_interest\nINTERVIEW_SCHEDULED: interview_scheduled\nINTERVIEW_COMPLETED: interview_completed';
COMMENT ON TABLE "applications" IS 'Отклик кандидата на конкретную вакансию.';
CREATE TABLE IF NOT EXISTS "employer_decisions" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "action" VARCHAR(30) NOT NULL,
    "reject_reason" VARCHAR(50),
    "created_at" TIMESTAMPTZ NOT NULL,
    "application_id" BIGINT NOT NULL REFERENCES "applications" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_employer_de_applica_8cdbbe" ON "employer_decisions" ("application_id");
COMMENT ON COLUMN "employer_decisions"."action" IS 'REJECTED: rejected\nRESERVED: reserved\nINVITED: invited';
COMMENT ON COLUMN "employer_decisions"."reject_reason" IS 'EXPERIENCE: experience\nSALARY: salary\nSCHEDULE: schedule\nLOCATION: location\nAVAILABLE_FROM: available_from\nOTHER: other';
COMMENT ON TABLE "employer_decisions" IS 'История решений работодателя по отклику.';
CREATE TABLE IF NOT EXISTS "matches" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "application_id" BIGINT NOT NULL UNIQUE REFERENCES "applications" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "matches" IS 'Факт взаимного интереса. На один отклик приходится не более одного match.';
CREATE TABLE IF NOT EXISTS "screening_answers" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "value" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "application_id" BIGINT NOT NULL REFERENCES "applications" ("id") ON DELETE CASCADE,
    "question_id" BIGINT NOT NULL REFERENCES "screening_questions" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_screening_a_applica_b02ccf" UNIQUE ("application_id", "question_id")
);
COMMENT ON TABLE "screening_answers" IS 'Ответ кандидата на вопрос первичного отбора в рамках конкретного отклика.';
CREATE TABLE IF NOT EXISTS "interview_slots" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "starts_at" TIMESTAMPTZ NOT NULL,
    "ends_at" TIMESTAMPTZ NOT NULL,
    "status" VARCHAR(20) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "employer_id" BIGINT NOT NULL REFERENCES "users" ("user_id") ON DELETE CASCADE,
    "vacancy_id" BIGINT NOT NULL REFERENCES "vacancies" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_interview_s_starts__c977e0" ON "interview_slots" ("starts_at");
CREATE INDEX IF NOT EXISTS "idx_interview_s_vacancy_43a2c7" ON "interview_slots" ("vacancy_id");
COMMENT ON COLUMN "interview_slots"."status" IS 'AVAILABLE: available\nBOOKED: booked\nCANCELLED: cancelled';
COMMENT ON TABLE "interview_slots" IS 'Доступный временной интервал работодателя для собеседования.';
CREATE TABLE IF NOT EXISTS "interviews" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(30) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "match_id" BIGINT NOT NULL UNIQUE REFERENCES "matches" ("id") ON DELETE CASCADE,
    "slot_id" BIGINT NOT NULL UNIQUE REFERENCES "interview_slots" ("id") ON DELETE RESTRICT
);
COMMENT ON COLUMN "interviews"."status" IS 'SCHEDULED: scheduled\nCOMPLETED: completed\nCANCELLED: cancelled\nNO_SHOW: no_show';
COMMENT ON TABLE "interviews" IS 'Назначенное или проведённое собеседование.';
CREATE TABLE IF NOT EXISTS "analytics_events" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "event_name" VARCHAR(100) NOT NULL,
    "payload" JSONB,
    "timestamp" TIMESTAMPTZ NOT NULL,
    "user_id" BIGINT REFERENCES "users" ("user_id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_analytics_e_event_n_ca0bd7" ON "analytics_events" ("event_name");
CREATE INDEX IF NOT EXISTS "idx_analytics_e_timesta_5c7aa4" ON "analytics_events" ("timestamp");
COMMENT ON TABLE "analytics_events" IS 'Событие пользовательского пути.';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "P2Y//x89nXXK"
)
