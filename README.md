# Cartographie de dose de la casemate C2

Application Streamlit de démonstration (formation Python NUVIA 2026, données fictives).

```bash
pip install -r requirements.txt
streamlit run app.py
```

Pas d'export PNG (kaleido absent), les livrables Word et PowerPoint
portent une mention à la place des figures.

## Connexion

L'application demande un utilisateur et un mot de passe, lus dans les secrets
(jamais dans le dépôt). Sur Streamlit Cloud : Settings > Secrets. En local :
`.streamlit/secrets.toml` (ignoré par git).

```toml
[comptes]
nuvia = "mot-de-passe"
```

Sans section `[comptes]`, personne n'entre.
