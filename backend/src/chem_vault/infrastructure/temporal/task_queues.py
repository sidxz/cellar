"""Temporal task queue constants.

Single queue for now. Split CPU-bound vs IO-bound later when
curve fitting / Markush activities arrive.
"""

MAIN_TASK_QUEUE = "chem-vault-main"

# Number of CDD/bulk molecules per processing chunk
CHUNK_SIZE = 250
