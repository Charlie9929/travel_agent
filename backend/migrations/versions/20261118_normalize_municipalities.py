"""Normalize direct municipalities to province-level city selections.

Revision ID: 20261118_municipalities
Revises: 20261115_trip_city_adcodes
"""

from alembic import op

revision: str = "20261118_municipalities"
down_revision: str | None = "20261115_trip_city_adcodes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    mappings = (
        ("北京市", "110000", "11"),
        ("天津市", "120000", "12"),
        ("上海市", "310000", "31"),
        ("重庆市", "500000", "50"),
    )
    for city_name, city_adcode, prefix in mappings:
        op.execute(
            f"""
            UPDATE trip
            SET city = '{city_name}', city_adcode = '{city_adcode}'
            WHERE city_adcode LIKE '{prefix}____'
               OR city IN ('{city_name.removesuffix("市")}城区', '{city_name}城区')
            """
        )
        extra_origin = (
            " OR origin_city IN ('重庆郊县', '重庆市郊县')"
            if prefix == "50"
            else ""
        )
        op.execute(
            f"""
            UPDATE trip
            SET origin_city = '{city_name}', origin_city_adcode = '{city_adcode}'
            WHERE origin_city_adcode LIKE '{prefix}____'
               OR origin_city IN ('{city_name.removesuffix("市")}城区', '{city_name}城区')
               {extra_origin}
            """
        )
    op.execute(
        """
        UPDATE trip
        SET city = '重庆市', city_adcode = '500000'
        WHERE city IN ('重庆郊县', '重庆市郊县')
        """
    )


def downgrade() -> None:
    # Canonical municipality values are valid in both schemas. Restoring the
    # provider's synthetic "城区/郊县" labels would reintroduce ambiguity.
    pass

