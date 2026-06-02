#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
  CREATE DATABASE democrai_core;
  CREATE DATABASE democrai_data;
  CREATE DATABASE democrai_observability;
  CREATE DATABASE democrai_ui_state;
SQL
