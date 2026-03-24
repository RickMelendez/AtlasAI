"""
Script de test rapido para verificar que Claude adapter funciona.

Este script prueba:
1. Que Claude adapter se inicializa correctamente
2. Que puede generar respuestas
3. Que el master prompt esta funcionando
"""

import asyncio
import sys
import os

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.adapters.ai.claude_adapter import get_claude_adapter


async def test_claude_integration():
    """Test basico de integracion con Claude."""

    print("=" * 60)
    print("ATLAS AI - TEST DE CLAUDE INTEGRATION")
    print("=" * 60)
    print()

    # Test 1: Inicializacion
    print("[Test 1] Inicializacion de Claude Adapter")
    try:
        claude = get_claude_adapter()
        print("[OK] Claude adapter inicializado correctamente")
        print(f"   Modelo: {claude.model}")
        print()
    except Exception as e:
        print(f"[ERROR] Error al inicializar Claude adapter: {e}")
        return

    # Test 2: Respuesta simple
    print("[Test 2] Generar respuesta simple")
    try:
        response = await claude.generate_response(
            user_message="Hola Atlas, como estas?",
            language="es"
        )
        print("[OK] Respuesta generada:")
        print(f"   {response}")
        print()
    except Exception as e:
        print(f"[ERROR] Error al generar respuesta: {e}")
        print(f"   Detalle: {str(e)}")
        return

    # Test 3: Respuesta con contexto de pantalla
    print("[Test 3] Respuesta con contexto de pantalla")
    try:
        screen_context = """
        Visual Studio Code
        Line 42: TypeError: Cannot read property 'name' of undefined
        at getUserData (user.ts:42:20)
        """

        response = await claude.generate_response(
            user_message="Que error ves en mi pantalla?",
            screen_context=screen_context,
            language="es"
        )
        print("[OK] Respuesta con contexto generada:")
        print(f"   {response}")
        print()
    except Exception as e:
        print(f"[ERROR] Error al generar respuesta con contexto: {e}")
        return

    # Test 4: Analisis de error
    print("[Test 4] Analisis de error en pantalla")
    try:
        screen_text = """
        src/components/User.tsx:42:20
        TypeError: Cannot read property 'name' of undefined

        Stack trace:
        at getUserData (user.ts:42:20)
        at UserComponent.render (User.tsx:15:10)
        """

        analysis = await claude.analyze_screen_context(
            screen_text=screen_text,
            app_context="vscode",
            language="es"
        )
        print("[OK] Analisis de error completado:")
        print(f"   Tiene error: {analysis.get('has_error')}")
        print(f"   Tipo: {analysis.get('error_type')}")
        print(f"   Urgencia: {analysis.get('urgency')}")
        print(f"   Sugerencia: {analysis.get('suggested_help', 'N/A')[:100]}...")
        print()
    except Exception as e:
        print(f"[ERROR] Error al analizar pantalla: {e}")
        return

    # Test 5: Ayuda proactiva
    print("[Test 5] Determinar ayuda proactiva")
    try:
        screen_context = """
        TypeError: Cannot read property 'name' of undefined
        at line 42 in user.ts
        """

        suggestion = await claude.offer_proactive_help(
            screen_context=screen_context,
            language="es"
        )

        if suggestion:
            print("[OK] Ayuda proactiva ofrecida:")
            print(f"   {suggestion}")
        else:
            print("[INFO] No se necesita ayuda proactiva en este contexto")
        print()
    except Exception as e:
        print(f"[ERROR] Error al determinar ayuda proactiva: {e}")
        return

    print("=" * 60)
    print("[SUCCESS] TODOS LOS TESTS PASARON CORRECTAMENTE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_claude_integration())
