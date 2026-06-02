# Specification: Main Data Storage Layer

Il layer `storage/data` gestisce il database principale dei dati dell'applicazione. A differenza di `democrai.db` (che contiene preferenze e configurazioni core), questo database contiene i dati operativi, i contenuti dei module e le informazioni degli utenti.

## Requisiti
1.  **Multi-Backend**: Supporto per SQLite (default locale) e PostgreSQL (server-side).
2.  **Module Isolation**: I module devono poter definire le proprie tabelle senza conflitti.
3.  **User Isolation**: Ogni record deve essere legato a un `user_id` per garantire la multi-tenancy futura.
4.  **Modular Migrations**: Le migrazioni del core e dei module devono essere coordinate.

## Architettura

### 1. Database Abstraction
Utilizzeremo **SQLAlchemy** come ORM per garantire la compatibilità tra SQLite e PostgreSQL. La stringa di connessione sarà configurabile.

### 2. Nomenclatura Tabelle
Per evitare conflitti tra module:
- Tabelle Core: `core_{table_name}`
- Tabelle Module: `p_{module_name}_{table_name}`

### 3. User Isolation (Multi-tenancy)
Ogni tabella operativa deve ereditare da un `UserMixin`:
```python
class UserMixin:
    user_id = Column(String, index=True, nullable=False)
```
Tutte le query devono (per policy o tramite layer di servizio) includere il filtro `user_id`.

### 4. Gestione Module
I module possono registrare i propri modelli SQLAlchemy. Il `ModuleManager` o un `DataStoreManager` raccoglierà i metadati dei module.

### 5. Migrazioni (Alembic)
Avremo un'istanza di Alembic dedicata a questo database.
- Le migrazioni del Core risiedono in `core/infrastructure/storage/data/migrations`.
- Le migrazioni dei module potrebbero risiedere all'interno dei module stessi, ma verranno orchestrate dal core.

## Struttura Proposta
- `base.py`: Definizioni comuni e interfacce.
- `models.py`: Modelli core del data DB.
- `mixins.py`: `UserMixin` e utility per l'isolamento.
- `database.py`: Gestione Engine, Session e connessione (configurabile).
- `migrations_handler.py`: Orchestratore migrazioni core + module.
- `factory.py`: Factory per ottenere lo store configurato.

## Sicurezza e Performance
- Utilizzo di `JSON` type (SQLAlchemy `JSON` o `Text` castato) per schemi flessibili nei module.
- Indici obbligatori su `user_id`.
- Foreign keys con `ON DELETE CASCADE` dove possibile (attenzione alle differenze tra SQLite/Postgres).
