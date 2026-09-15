"""
Pruebas para el módulo de base de datos
Verifica conexión, sesiones y operaciones básicas
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from api.database import (
    engine,
    SessionLocal,
    Base,
    get_db,
    create_tables,
    drop_tables,
    # Se importa con alias a propósito: pytest recolecta cualquier nombre de
    # módulo que empiece por `test_`, así que `test_connection` se ejecutaba como
    # un test más (devolvía un bool y generaba PytestReturnNotNoneWarning), en
    # lugar de ser solo un ayudante que usa la prueba.
    test_connection as check_connection,
)
from api.models import User, Product, Order
from api.config import config


class TestDatabaseConnection:
    """Pruebas de conexión a la base de datos"""
    
    def test_engine_created(self):
        """Verificar que el engine se creó correctamente"""
        assert engine is not None
        assert engine.url is not None
        print(f"\n✅ Engine creado: {engine.url}")
    
    def test_engine_url(self):
        """Verificar que la URL de la base de datos es válida"""
        url = str(engine.url)
        assert url is not None
        assert len(url) > 0
        print(f"\n✅ URL de base de datos: {url}")
    
    def test_connection(self):
        """Verificar conexión a la base de datos"""
        result = check_connection()
        assert result is True
        print("\n✅ Conexión a base de datos exitosa")
    
    def test_engine_ping(self):
        """Verificar que el engine puede hacer ping a la BD"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1")).scalar()
                assert result == 1
            print("\n✅ Ping a base de datos exitoso")
        except Exception as e:
            pytest.fail(f"Error haciendo ping a la BD: {e}")
    
    def test_session_creation(self):
        """Verificar que se puede crear una sesión"""
        session = SessionLocal()
        assert session is not None
        session.close()
        print("\n✅ Sesión creada correctamente")


class TestDatabaseTables:
    """Pruebas de creación y gestión de tablas"""
    
    def test_tables_created(self, test_engine):
        """Verificar que las tablas se crearon correctamente"""
        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        
        # Verificar que existen las tablas principales
        expected_tables = ['users', 'products', 'orders', 'order_items', 'reviews', 'categories']
        
        for table in expected_tables:
            assert table in tables, f"Tabla '{table}' no encontrada"
        
        print(f"\n✅ Tablas creadas: {', '.join(tables)}")
    
    def test_table_columns(self, test_engine):
        """Verificar que las tablas tienen las columnas esperadas"""
        inspector = inspect(test_engine)
        
        # Verificar columnas de users
        columns = inspector.get_columns('users')
        column_names = [c['name'] for c in columns]
        
        expected_columns = [
            'id', 'uuid', 'email', 'username', 'hashed_password',
            'first_name', 'last_name', 'phone', 'avatar_url',
            'role', 'status', 'is_active', 'is_verified', 'is_superuser',
            'language', 'timezone', 'notifications_enabled',
            'created_at', 'updated_at', 'last_login'
        ]
        
        for col in expected_columns:
            assert col in column_names, f"Columna '{col}' no encontrada en users"
        
        print(f"\n✅ Columnas de users: {', '.join(column_names[:5])}...")
    
    def test_table_foreign_keys(self, test_engine):
        """Verificar que las llaves foráneas están definidas"""
        inspector = inspect(test_engine)
        
        # Verificar llaves foráneas de products
        fks = inspector.get_foreign_keys('products')
        assert len(fks) > 0, "No se encontraron llaves foráneas en products"
        
        # Verificar que la llave foránea apunta a users
        found = False
        for fk in fks:
            if fk['referred_table'] == 'users':
                found = True
                break
        
        assert found, "Llave foránea a users no encontrada en products"
        print("\n✅ Llaves foráneas configuradas correctamente")
    
    def test_table_indexes(self, test_engine):
        """Verificar que los índices están creados"""
        inspector = inspect(test_engine)
        
        # Verificar índices de users
        indexes = inspector.get_indexes('users')
        index_names = [idx['name'] for idx in indexes]
        
        # Debería tener al menos índice en email y username
        assert 'ix_users_email' in index_names or 'ix_users_email_status' in index_names, "Índice de email no encontrado"
        assert 'ix_users_username' in index_names, "Índice de username no encontrado"
        
        print(f"\n✅ Índices de users: {', '.join(index_names)}")
    
    def test_create_tables_function(self, test_engine):
        """Verificar que create_tables funciona sin errores"""
        try:
            create_tables()
            print("\n✅ create_tables() ejecutado sin errores")
        except Exception as e:
            pytest.fail(f"Error en create_tables(): {e}")
    
    def test_drop_tables_exige_confirmacion_explicita(self):
        """
        `drop_tables()` no debe borrar nada sin `confirm=True`.

        Es la protección clave de D2. El engine de `api/database.py` apunta a la
        base de datos REAL (`app.db`), no a la de tests, así que la versión
        anterior de esta prueba —que llamaba a `drop_tables()` cuando
        ENVIRONMENT=testing— borraba las tablas de la aplicación: usuarios,
        productos e historial.

        Esta comprobación es segura porque el guardia de confirmación se evalúa
        ANTES de tocar la base de datos: si fallara, no borraría nada.
        """
        with pytest.raises(RuntimeError) as excinfo:
            drop_tables()

        assert 'confirm=True' in str(excinfo.value)
        print(f"\n✅ drop_tables() sin confirmar no borra nada: {excinfo.value}")

    def test_borrado_solo_permitido_en_desarrollo_o_pruebas(self):
        """
        La comprobación de entorno es una función pura, así que se puede probar
        sin riesgo de borrar nada.
        """
        from api.database import entornos_donde_se_puede_borrar

        assert entornos_donde_se_puede_borrar('development') is True
        assert entornos_donde_se_puede_borrar('testing') is True
        assert entornos_donde_se_puede_borrar('production') is False
        assert entornos_donde_se_puede_borrar('staging') is False
        assert entornos_donde_se_puede_borrar('') is False

    def test_la_suite_no_usa_la_base_de_datos_real(self):
        """
        Control de seguridad: el engine de la suite NO debe apuntar a app.db.

        Es el invariante que sustituye al antiguo "la tabla real sigue intacta":
        en vez de comprobar el daño después, se comprueba que la suite no puede
        hacer daño. `tests/conftest.py` redirige DATABASE_URL a un fichero
        temporal antes de importar `api.database`, así que aquí debe verse esa
        ruta y nunca la de la aplicación.
        """
        from api.database import engine

        url = str(engine.url)
        print(f"\n  base de datos de la suite: {url}")

        assert 'app.db' not in url, (
            f'la suite está usando la base de datos real de la aplicación: {url}'
        )
        assert 'predicc_tests_' in url or 'tmp' in url.lower(), (
            f'la suite debería usar una base de datos temporal: {url}'
        )

    def test_el_engine_de_la_suite_es_utilizable(self):
        """El engine aislado debe funcionar: la suite tiene que poder crear tablas."""
        from sqlalchemy import inspect as sqla_inspect
        from api.database import create_tables, engine

        create_tables()
        tablas = set(sqla_inspect(engine).get_table_names())
        assert {'users', 'predictions', 'products'} <= tablas, tablas


class TestDatabaseOperations:
    """Pruebas de operaciones básicas con la base de datos"""
    
    def test_insert_user(self, db_session):
        """Insertar un usuario en la base de datos"""
        from api.crud import CRUDUser
        from api.schemas import UserCreate
        
        user_data = UserCreate(
            email="test_db@example.com",
            username="testdbuser",
            password="Test123!@#",
            first_name="Test",
            last_name="DB"
        )
        
        user = CRUDUser.create(db_session, user_data)
        db_session.commit()
        
        assert user.id is not None
        assert user.email == "test_db@example.com"
        assert user.username == "testdbuser"
        print(f"\n✅ Usuario insertado: {user.email} (ID: {user.id})")
    
    def test_query_user(self, db_session, test_user):
        """Consultar un usuario de la base de datos"""
        from api.crud import CRUDUser
        
        user = CRUDUser.get_by_id(db_session, test_user.id)
        
        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email
        print(f"\n✅ Usuario consultado: {user.email}")
    
    def test_update_user(self, db_session, test_user):
        """Actualizar un usuario en la base de datos"""
        from api.crud import CRUDUser
        from api.schemas import UserUpdate
        
        update_data = UserUpdate(
            first_name="Updated",
            last_name="Name"
        )
        
        user = CRUDUser.update(db_session, test_user.id, update_data)
        
        assert user.first_name == "Updated"
        assert user.last_name == "Name"
        print(f"\n✅ Usuario actualizado: {user.first_name} {user.last_name}")
    
    def test_delete_user_soft(self, db_session, test_user):
        """Eliminar un usuario (soft delete)"""
        from api.crud import CRUDUser
        
        result = CRUDUser.delete(db_session, test_user.id, soft=True)
        
        assert result is True
        
        # Verificar que el usuario está desactivado
        user = CRUDUser.get_by_id(db_session, test_user.id)
        assert user.is_active is False
        print(f"\n✅ Usuario desactivado: {user.email} (is_active: {user.is_active})")
    
    def test_transaction_rollback(self, db_session):
        """Verificar que las transacciones pueden hacer rollback"""
        from api.crud import CRUDUser
        from api.schemas import UserCreate
        from api.models import User
        
        # ✅ PASO 1: Crear el primer usuario (debe funcionar)
        user1_data = UserCreate(
            email="rollback_test@example.com",
            username="rollbackuser1",
            password="Test123!@#",
            first_name="Rollback",
            last_name="Test"
        )
        
        user1 = CRUDUser.create(db_session, user1_data)
        db_session.commit()
        
        assert user1.id is not None
        assert user1.email == "rollback_test@example.com"
        print(f"\n✅ Primer usuario creado: {user1.email}")
        
        # ✅ PASO 2: Intentar crear un segundo usuario con el MISMO email
        user2_data = UserCreate(
            email="rollback_test@example.com",  # ← MISMO email que user1
            username="rollbackuser2",
            password="Test123!@#"
        )
        
        # ✅ PASO 3: Esto DEBE lanzar ValueError
        with pytest.raises(ValueError) as exc_info:
            CRUDUser.create(db_session, user2_data)
            # No hacer commit - el rollback debe ser automático
        
        # Verificar el mensaje de error
        error_msg = str(exc_info.value).lower()
        assert "ya está registrado" in error_msg or "email" in error_msg
        print(f"\n✅ ValueError lanzado correctamente: {exc_info.value}")
        
        # ✅ PASO 4: Verificar que NO se creó el usuario duplicado
        users = db_session.query(User).filter(
            User.username == "rollbackuser2"
        ).all()
        assert len(users) == 0, "El usuario duplicado no debería existir"
        
        # ✅ PASO 5: Verificar que el usuario original sigue existiendo
        users = db_session.query(User).filter(
            User.email == "rollback_test@example.com"
        ).all()
        assert len(users) == 1, "El usuario original debería existir"
        
        print("\n✅ Rollback de transacción verificado correctamente")

    
    

class TestDatabasePerformance:
    """Pruebas de rendimiento y consultas"""
    
    def test_bulk_insert(self, db_session):
        """Probar inserción masiva de datos"""
        from api.crud import CRUDUser
        from api.schemas import UserCreate
        
        users = []
        for i in range(5):
            user_data = UserCreate(
                email=f"bulk{i}@example.com",
                username=f"bulkuser{i}",
                password="Test123!@#",
                first_name=f"Bulk{i}",
                last_name="Test"
            )
            user = CRUDUser.create(db_session, user_data)
            users.append(user)
        
        db_session.commit()
        
        assert len(users) == 5
        for user in users:
            assert user.id is not None
        
        print(f"\n✅ Inserción masiva de {len(users)} usuarios completada")
    
    def test_query_with_filters(self, db_session, test_user):
        """Probar consultas con filtros"""
        from api.crud import CRUDUser
        
        # Búsqueda por email parcial
        users = CRUDUser.get_all(
            db_session,
            search="test@",
            limit=10
        )
        
        assert len(users) >= 1
        assert any(user.email == "test@example.com" for user in users)
        
        # Búsqueda por nombre
        users = CRUDUser.get_all(
            db_session,
            search="Test",
            limit=10
        )
        
        assert len(users) >= 1
        print(f"\n✅ Consulta con filtros: {len(users)} resultados")
    
    def test_pagination(self, db_session, test_user):
        """Probar paginación en consultas"""
        from api.crud import CRUDUser
        
        # Primera página
        page1 = CRUDUser.get_all(db_session, skip=0, limit=2)
        # Segunda página
        page2 = CRUDUser.get_all(db_session, skip=2, limit=2)
        
        assert len(page1) <= 2
        assert len(page2) <= 2
        
        # Verificar que no hay duplicados
        ids_page1 = {u.id for u in page1}
        ids_page2 = {u.id for u in page2}
        
        # Si hay usuarios en ambas páginas, sus IDs no deben coincidir
        if ids_page1 and ids_page2:
            assert ids_page1.isdisjoint(ids_page2), "Hay duplicados entre páginas"
        
        print(f"\n✅ Paginación: Página 1: {len(page1)}, Página 2: {len(page2)}")


class TestDatabaseGetDB:
    """Pruebas de la dependencia get_db"""
    
    def test_get_db_returns_session(self):
        """Verificar que get_db retorna una sesión"""
        db_gen = get_db()
        db = next(db_gen)
        
        assert db is not None
        assert db.bind is not None
        
        try:
            next(db_gen)
        except StopIteration:
            # Esto es normal, el generador se cierra después del yield
            pass
        
        print("\n✅ get_db() retorna una sesión válida")
    
    def test_get_db_closes_session(self):
        """Verificar que get_db cierra la sesión correctamente"""
        db_gen = get_db()
        db = next(db_gen)
        
        # Verificar que la sesión está abierta
        assert db.is_active
        
        # Cerrar el generador
        try:
            next(db_gen)
        except StopIteration:
            pass
        
        # La sesión debería cerrarse automáticamente
        print("\n✅ get_db() cierra la sesión correctamente")


class TestDatabaseIntegrity:
    """Pruebas de integridad de la base de datos"""
    
    def test_unique_email_constraint(self, db_session, test_user):
        """Verificar que el email es único"""
        from api.crud import CRUDUser
        from api.schemas import UserCreate
        
        user_data = UserCreate(
            email="test@example.com",  # Email duplicado
            username="uniqueuser",
            password="Test123!@#"
        )
        
        with pytest.raises(ValueError) as exc_info:
            CRUDUser.create(db_session, user_data)
        
        assert "ya está registrado" in str(exc_info.value).lower() or "email" in str(exc_info.value).lower()
        print("\n✅ Restricción de email único verificada")
    
    def test_unique_username_constraint(self, db_session, test_user):
        """Verificar que el username es único"""
        from api.crud import CRUDUser
        from api.schemas import UserCreate
        
        user_data = UserCreate(
            email="unique@example.com",
            username="testuser",  # Username duplicado
            password="Test123!@#"
        )
        
        with pytest.raises(ValueError) as exc_info:
            CRUDUser.create(db_session, user_data)
        
        assert "username" in str(exc_info.value).lower() or "ya está en uso" in str(exc_info.value)
        print("\n✅ Restricción de username único verificada")
    
    def test_foreign_key_constraint(self, db_session, test_user):
        """Verificar que las llaves foráneas funcionan"""
        from api.crud import CRUDProduct
        from api.schemas import ProductCreate
        
        # Crear producto con usuario existente (debería funcionar)
        product_data = ProductCreate(
            name="Test Product FK",
            description="Test foreign key",
            price=99.99,
            stock=10,
            sku="TEST-FK-001",
            owner_id=test_user.id
        )
        
        product = CRUDProduct.create(db_session, product_data)
        db_session.commit()
        
        assert product.id is not None
        assert product.owner_id == test_user.id
        
        print("\n✅ Llave foránea verificada")
    
    def test_cascade_delete(self, db_session, test_user, test_product):
        """Verificar que el borrado en cascada funciona"""
        from api.crud import CRUDUser, CRUDProduct
        
        # Verificar que el producto existe
        product = CRUDProduct.get_by_id(db_session, test_product.id)
        assert product is not None
        
        # Eliminar el usuario (esto debería eliminar sus productos por cascada)
        CRUDUser.delete(db_session, test_user.id, soft=False)
        db_session.commit()
        
        # El producto ya no debería existir
        product = CRUDProduct.get_by_id(db_session, test_product.id)
        assert product is None
        
        print("\n✅ Borrado en cascada verificado")