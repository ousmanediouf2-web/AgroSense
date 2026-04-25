# 🌱 AgroSense — Station Météo Agricole IoT

> Projet IoT complet : capteurs agricoles, base de données MongoDB, API Flask et interface web moderne — le tout orchestré avec **Docker Compose**.

---

## 📁 Structure du projet

```
agro_iot/
├── 🐳 Dockerfile              # Image Python/Flask
├── 🐳 docker-compose.yml      # Orchestration des 3 services
├── 🐍 app.py                  # Backend Flask + API REST
├── 📦 requirements.txt        # Dépendances Python
├── 🔧 .env.example            # Variables d'environnement (modèle)
├── 🚀 start.sh                # Script de démarrage rapide
├── 📂 mongo-init/
│   └── init.js                # Script d'init MongoDB (index, utilisateur)
├── 📂 static/
│   └── index.html             # Interface web SPA
└── 📖 README.md               # Ce fichier
```

---

## 🐳 Services Docker

| Service | Image | Port | Rôle |
|---------|-------|------|------|
| mongo | mongo:7.0 | 27017 | Base de données MongoDB |
| mongo-express | mongo-express:1.0.2 | 8081 | Interface admin MongoDB |
| backend | Image buildée localement | 5000 | API Flask + Interface web |

---

## 🚀 Démarrage rapide

### Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et lancé
- Aucune autre installation nécessaire (pas de Python, pas de MongoDB local)

### 1. Se placer dans le dossier

```bash
cd agro_iot/
```

### 2. Démarrer avec le script (recommandé)

```bash
# Linux / Mac
chmod +x start.sh
./start.sh

# Windows (PowerShell)
docker compose up -d --build
```

### 3. Accéder aux interfaces

| Interface | URL | Identifiants |
|-----------|-----|-------------|
| Application principale | http://localhost:5000 | — |
| Admin MongoDB | http://localhost:8081 | admin / admin123 |

> ⏳ Patientez ~30 secondes au premier démarrage : MongoDB doit initialiser avant que le backend se connecte.

---

## 🛠 Commandes utiles

```bash
# Voir l'état des conteneurs
./start.sh status

# Voir les logs en temps réel
./start.sh logs

# Arrêter les conteneurs (données conservées)
./start.sh down

# Réinitialiser complètement (supprime les données)
./start.sh reset

# Rebuild de l'image backend seulement
docker compose build backend && docker compose up -d backend

# Shell MongoDB
docker exec -it agro_mongo mongosh -u agro_user -p agro_pass --authenticationDatabase admin

# Shell backend
docker exec -it agro_backend bash
```

---

## 🗄️ Modèle de données

### Collection capteurs

```json
{
  "capteur_id": "CAP-P1-TEMP-01",
  "parcelle":   "Parcelle A",
  "type":       "température",
  "unite":      "°C"
}
```

### Collection mesures

```json
{
  "capteur_id": "CAP-P1-TEMP-01",
  "parcelle":   "Parcelle A",
  "type":       "température",
  "valeur":     27.5,
  "unite":      "°C",
  "timestamp":  ISODate("2024-01-15T14:30:00Z")
}
```

---

## 🌐 API REST

| Route | Description |
|-------|-------------|
| GET /api/capteurs | Liste tous les capteurs |
| GET /api/parcelles | Liste les parcelles |
| GET /api/mesures | Mesures filtrées (parcelle, type, heures, limit) |
| GET /api/stats/moyenne_temperature | Moyennes T° par parcelle 24h |
| GET /api/alertes | Anomalies détectées (seuil_hum, seuil_temp) |
| GET /api/evolution_horaire/<id> | Évolution horaire d'un capteur |
| GET /api/dashboard | KPIs synthétiques |

---

## 🔍 Requêtes MongoDB

```javascript
// Moyenne température par parcelle (24h)
db.mesures.aggregate([
  { $match: { type: "température", timestamp: { $gte: new Date(Date.now() - 86400000) } } },
  { $group: { _id: "$parcelle", moyenne: { $avg: "$valeur" }, min: { $min: "$valeur" }, max: { $max: "$valeur" } } },
  { $sort: { _id: 1 } }
])

// Alertes humidité < 30%
db.mesures.find({
  type: "humidité", valeur: { $lt: 30 },
  timestamp: { $gte: new Date(Date.now() - 86400000) }
}).sort({ timestamp: -1 })

// Évolution horaire
db.mesures.aggregate([
  { $match: { capteur_id: "CAP-P1-HUM-01", timestamp: { $gte: new Date(Date.now() - 86400000) } } },
  { $group: { _id: { $hour: "$timestamp" }, moyenne: { $avg: "$valeur" } } },
  { $sort: { _id: 1 } }
])
```

---

## 🐛 Résolution de problèmes

| Problème | Solution |
|----------|----------|
| Port 5000 occupé | Changer "5000:5000" en "5001:5000" dans docker-compose.yml |
| Backend démarre trop vite | Attendre 30-40s ou relancer avec docker compose restart backend |
| Erreur permission start.sh | chmod +x start.sh |
| Reset complet | docker compose down -v puis docker compose up -d --build |
