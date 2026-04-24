# SYN — Commandes de démarrage et test

## 1. Démarrer l'infrastructure Docker

```powershell
docker compose up -d
```

Vérifier que les services sont healthy :
```powershell
docker compose ps
```

## 2. Setup venv et installation des dépendances

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Copier et configurer le .env

```powershell
Copy-Item .env.example .env
# Éditer .env : renseigner NCBI_EMAIL
notepad .env
```

## 4. Démarrer FastAPI (hot-reload)

```powershell
uvicorn app.main:app --reload
```

L'API est disponible sur http://localhost:8000
Swagger UI : http://localhost:8000/docs

## 5. Tests end-to-end

### Health check
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health"
```

### Ingestion ClinicalTrials.gov
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/ingest/trials?query=pembrolizumab&max_results=50" -Method POST
```

### Recherche sémantique
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/trials/search?q=checkpoint+inhibitor+lung+cancer&phase=PHASE3"
```

### Détail d'un essai (remplacer NCT_ID par un ID réel)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/trials/NCT04030195"
```

### Ingestion PubMed
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/ingest/pubmed?query=pembrolizumab+NSCLC&max_results=20" -Method POST
```

## 6. Vérification PostgreSQL

```powershell
# Compter les essais insérés
docker exec syn-postgres psql -U syn -d syn -c "SELECT COUNT(*) FROM clinical_trials;"

# Voir les phases distinctes
docker exec syn-postgres psql -U syn -d syn -c "SELECT phase, COUNT(*) FROM clinical_trials GROUP BY phase ORDER BY COUNT(*) DESC;"

# Voir les statuts
docker exec syn-postgres psql -U syn -d syn -c "SELECT status, COUNT(*) FROM clinical_trials GROUP BY status ORDER BY COUNT(*) DESC;"

# Top 5 sponsors
docker exec syn-postgres psql -U syn -d syn -c "SELECT sponsor, COUNT(*) FROM clinical_trials GROUP BY sponsor ORDER BY COUNT(*) DESC LIMIT 5;"
```

## 7. Migrations Alembic (quand le schéma évolue)

```powershell
# Générer une migration automatique
alembic revision --autogenerate -m "description"

# Appliquer les migrations
alembic upgrade head

# État des migrations
alembic current
```

## Validation finale

Ces 3 commandes doivent fonctionner sans erreur :

```powershell
# 1. Ingestion réelle
Invoke-RestMethod -Uri "http://localhost:8000/ingest/trials?query=pembrolizumab&max_results=50" -Method POST

# 2. Recherche sémantique avec résultats
Invoke-RestMethod -Uri "http://localhost:8000/trials/search?q=checkpoint+inhibitor+lung+cancer&phase=PHASE3"

# 3. Count PostgreSQL > 0
docker exec syn-postgres psql -U syn -d syn -c "SELECT COUNT(*) FROM clinical_trials;"
```
