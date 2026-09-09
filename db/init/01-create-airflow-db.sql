-- Runs once against the default `churn_platform` database on first init.
-- Creates a second database for Airflow's own metadata store (LocalExecutor),
-- reusing the same postgres container/user rather than running a second DB.
CREATE DATABASE airflow OWNER cmp_user;
