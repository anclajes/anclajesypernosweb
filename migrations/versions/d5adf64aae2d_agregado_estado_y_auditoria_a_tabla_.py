"""Agregado estado y auditoria a tabla productos

Revision ID: d5adf64aae2d
Revises: 
Create Date: 2026-06-19 11:23:21.974268

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5adf64aae2d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # No-op: las columnas 'estado', 'fecha_actualizacion' y 'actualizado_por'
    # de 'product' ya existen en producción. Las tablas de ImportBolts
    # se crean en la migración 438dfee9f739.
    pass


def downgrade():
    pass