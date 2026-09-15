# Artefactos de experimentos

Aquí van los modelos que **no** usa la aplicación. El modelo desplegado y sus
dependencias están un nivel arriba, en `models_saved/`:

| Fichero | Lo usa la API |
|---|---|
| `../RandomForest_Tuned.pkl` | ✅ Sí, es el modelo que predice |
| `../scaler.pkl` | ✅ Sí |
| `../feature_names.txt` | ✅ Sí |
| `../feature_contract.json` | ✅ Sí |
| `../feature_importance.csv` | ❌ No, es para los informes |
| `gradient_boosting.pkl` | ❌ No |

## gradient_boosting.pkl

Modelo de comparación que entrena `notebooks/02_model_training_ames.ipynb` para
elegir el mejor algoritmo. El Random Forest ganó, así que este Gradient Boosting
no se desplegó. Se conserva por trazabilidad del experimento.

> Nota: el notebook sigue guardando este fichero en `models_saved/` (no en
> `experiments/`). Si lo vuelves a ejecutar, aparecerá de nuevo arriba; muévelo
> aquí o ajusta la ruta en la celda correspondiente.

## Reproducir el modelo desplegado

```bash
python src/models/train_model.py
```

Regenera `RandomForest_Tuned.pkl`, `scaler.pkl`, `feature_names.txt`,
`feature_importance.csv`, `data/processed/` y el contrato de características.
