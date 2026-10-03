"""Package required to unpickle ``models/fare_prediction_pipeline.pkl``.

The pickle stores the *import path* of the custom transformer
(``project.transformer.DateTimeFeatureTransformer``), not its source code.
So this package name and module name must stay exactly as they are.
"""
