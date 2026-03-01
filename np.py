import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime, timedelta

# ============================================
# CONFIGURACIÓN DEL GRID BOT
# ============================================
rango_min = 3.71
rango_max = 4.61
rejillas = 14
apalancamiento = 75
fee = 0.0005  # 0.05% por operación
capital_por_bot = 20  # USDT por cada bot (Long y Short)

# ============================================
# DESCARGAR DATOS DE BINANCE
# ============================================
def descargar_velas_binance(symbol='FLUIDUSDT', interval='1m', limit=1000):
    """
    Descarga velas de 1 minuto de Binance Futures (FAPI) usando urllib
    limit: número de velas (máximo 1500 por request en futures)
    """
    import urllib.request
    import json
    
    # URL de Binance Futures API
    url = f'https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}'
    
    try:
        print(f"🔄 Descargando datos de {symbol}...")
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
        
        # Convertir a DataFrame
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # Convertir tipos de datos
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        
        print(f"✅ Descargadas {len(df)} velas de {symbol}")
        print(f"📅 Desde: {df['timestamp'].iloc[0]}")
        print(f"📅 Hasta: {df['timestamp'].iloc[-1]}")
        print(f"💰 Precio inicial: {df['open'].iloc[0]:.4f} USDT")
        print(f"💰 Precio final: {df['close'].iloc[-1]:.4f} USDT")
        print(f"📊 Rango datos: {df['low'].min():.4f} - {df['high'].max():.4f}")
        
        return df
    
    except Exception as e:
        print(f"❌ Error descargando datos: {e}")
        print(f"❌ Asegúrate de tener conexión a internet y que el símbolo {symbol} exista")
        return None

# ============================================
# SIMULACIÓN DUAL GRID BOT (SIMPLIFICADA Y CORRECTA)
# ============================================
def simular_dual_grid(df, rango_min, rango_max, num_rejillas, capital_bot, apalancamiento, fee):
    """
    Simula un DUAL GRID BOT de forma SIMPLE y CORRECTA:
    
    1. Define precios de compra y venta desde el inicio
    2. Inicializa posiciones según precio inicial
    3. Solo compra si NO hay posición abierta en ese nivel
    4. Solo vende si HAY posición abierta en ese nivel
    """
    
    # Generar niveles del grid
    niveles = np.linspace(rango_min, rango_max, num_rejillas + 1)
    spread = niveles[1] - niveles[0]
    cantidad_por_nivel = capital_bot / num_rejillas  # USDT por nivel
    
    print(f"\n📐 GRID CONFIGURADO:")
    print(f"   Niveles totales: {len(niveles)}")
    print(f"   Spread entre niveles: {spread:.6f} USDT ({(spread/rango_min)*100:.4f}%)")
    print(f"   Capital por nivel: {cantidad_por_nivel:.4f} USDT")
    print(f"   Tamaño posición con {apalancamiento}x: {cantidad_por_nivel * apalancamiento:.2f} USDT")
    
    # Estado inicial
    precio_inicial = df['open'].iloc[0]
    
    # Para cada nivel, guardar:
    # - Si tiene posición abierta (True/False)
    # - Precio de entrada de esa posición
    long_posiciones = {}  # {nivel_idx: precio_entrada} o vacío si no hay posición
    short_posiciones = {}
    
    # Definir niveles de compra y venta para cada bot
    # LONG: compra en cada nivel, vende en el nivel superior
    # SHORT: vende en cada nivel, compra en el nivel inferior
    
    print(f"\n💰 PRECIO INICIAL: {precio_inicial:.4f} USDT")
    
    # Encontrar nivel inicial más cercano
    nivel_inicial = np.argmin(np.abs(niveles - precio_inicial))
    print(f"   Nivel inicial: {nivel_inicial} (precio: {niveles[nivel_inicial]:.4f})")
    
    # Estadísticas
    long_profit = 0
    short_profit = 0
    long_operaciones = 0
    short_operaciones = 0
    fees_acumulados = 0
    
    # Historial
    long_profit_hist = []
    short_profit_hist = []
    fees_hist = []
    precio_hist = []
    
    razon_cierre = None
    precio_salida = None
    
    # INICIALIZAR POSICIONES SEGÚN PRECIO INICIAL
    print(f"\n🔧 INICIALIZANDO POSICIONES...")
    posiciones_long_iniciales = 0
    posiciones_short_iniciales = 0
    
    for i in range(len(niveles)):
        # LONG: comprar en niveles por DEBAJO del precio inicial
        if niveles[i] < niveles[nivel_inicial]:
            long_posiciones[i] = niveles[i]
            posiciones_long_iniciales += 1
            fees_acumulados += fee * apalancamiento * cantidad_por_nivel
            
        # SHORT: vender en niveles por ENCIMA del precio inicial  
        if niveles[i] > niveles[nivel_inicial]:
            short_posiciones[i] = niveles[i]
            posiciones_short_iniciales += 1
            fees_acumulados += fee * apalancamiento * cantidad_por_nivel
    
    print(f"   ✅ LONG: {posiciones_long_iniciales} posiciones compradas por debajo")
    print(f"   ✅ SHORT: {posiciones_short_iniciales} posiciones vendidas por encima")
    
    # Iterar vela por vela
    print(f"\n🔄 PROCESANDO {len(df)} VELAS...")
    
    for idx in range(len(df)):
        vela_high = df['high'].iloc[idx]
        vela_low = df['low'].iloc[idx]
        vela_close = df['close'].iloc[idx]
        
        # Verificar si salimos del rango
        if vela_high > rango_max:
            print(f"\n⚠️  RUPTURA ALCISTA en vela {idx}: Precio {vela_high:.4f} > {rango_max}")
            precio_salida = vela_high
            razon_cierre = "Ruptura ALCISTA"
            
            # Cerrar todas las posiciones
            for nivel_idx, precio_entrada in long_posiciones.items():
                ganancia_pct = (precio_salida - precio_entrada) / precio_entrada
                profit = ganancia_pct * apalancamiento * cantidad_por_nivel
                long_profit += profit
                fees_acumulados += fee * apalancamiento * cantidad_por_nivel
                
            for nivel_idx, precio_entrada in short_posiciones.items():
                perdida_pct = (precio_salida - precio_entrada) / precio_entrada
                profit = -perdida_pct * apalancamiento * cantidad_por_nivel
                short_profit += profit
                fees_acumulados += fee * apalancamiento * cantidad_por_nivel
            
            break
            
        elif vela_low < rango_min:
            print(f"\n⚠️  RUPTURA BAJISTA en vela {idx}: Precio {vela_low:.4f} < {rango_min}")
            precio_salida = vela_low
            razon_cierre = "Ruptura BAJISTA"
            
            # Cerrar todas las posiciones
            for nivel_idx, precio_entrada in long_posiciones.items():
                perdida_pct = (precio_entrada - precio_salida) / precio_entrada
                profit = -perdida_pct * apalancamiento * cantidad_por_nivel
                long_profit += profit
                fees_acumulados += fee * apalancamiento * cantidad_por_nivel
                
            for nivel_idx, precio_entrada in short_posiciones.items():
                ganancia_pct = (precio_entrada - precio_salida) / precio_entrada
                profit = ganancia_pct * apalancamiento * cantidad_por_nivel
                short_profit += profit
                fees_acumulados += fee * apalancamiento * cantidad_por_nivel
            
            break
        
        # Procesar cada nivel del grid
        for i in range(len(niveles)):
            nivel_precio = niveles[i]
            
            # Verificar si el precio tocó este nivel en esta vela
            if vela_low <= nivel_precio <= vela_high:
                
                # ========== LONG BOT ==========
                # COMPRA: Si NO tiene posición en este nivel Y el precio bajó hasta aquí
                if i not in long_posiciones:
                    long_posiciones[i] = nivel_precio
                    fees_acumulados += fee * apalancamiento * cantidad_por_nivel
                    if idx < 5:
                        print(f"   🟢 LONG COMPRA nivel {i} a {nivel_precio:.4f}")
                
                # VENTA: Si tiene posición en el nivel INFERIOR y el precio subió hasta aquí
                if i > 0 and (i-1) in long_posiciones:
                    precio_compra = long_posiciones[i-1]
                    ganancia_pct = (nivel_precio - precio_compra) / precio_compra
                    profit = ganancia_pct * apalancamiento * cantidad_por_nivel
                    long_profit += profit
                    long_operaciones += 1
                    fees_acumulados += fee * apalancamiento * cantidad_por_nivel
                    
                    # Cerrar la posición del nivel inferior
                    del long_posiciones[i-1]
                    
                    if idx < 5:
                        print(f"   🟢 LONG VENDE nivel {i-1} a {nivel_precio:.4f} - Profit: {profit:.4f}")
                
                # ========== SHORT BOT ==========
                # VENTA: Si NO tiene posición en este nivel Y el precio subió hasta aquí
                if i not in short_posiciones:
                    short_posiciones[i] = nivel_precio
                    fees_acumulados += fee * apalancamiento * cantidad_por_nivel
                    if idx < 5:
                        print(f"   🔴 SHORT VENDE nivel {i} a {nivel_precio:.4f}")
                
                # COMPRA: Si tiene posición en el nivel SUPERIOR y el precio bajó hasta aquí
                if i < len(niveles)-1 and (i+1) in short_posiciones:
                    precio_venta = short_posiciones[i+1]
                    ganancia_pct = (precio_venta - nivel_precio) / precio_venta
                    profit = ganancia_pct * apalancamiento * cantidad_por_nivel
                    short_profit += profit
                    short_operaciones += 1
                    fees_acumulados += fee * apalancamiento * cantidad_por_nivel
                    
                    # Cerrar la posición del nivel superior
                    del short_posiciones[i+1]
                    
                    if idx < 5:
                        print(f"   🔴 SHORT COMPRA nivel {i+1} a {nivel_precio:.4f} - Profit: {profit:.4f}")
        
        # Guardar historial
        long_profit_hist.append(long_profit)
        short_profit_hist.append(short_profit)
        fees_hist.append(fees_acumulados)
        precio_hist.append(vela_close)
    
    profit_neto_usdt = long_profit + short_profit - fees_acumulados
    profit_neto_pct = (profit_neto_usdt / (capital_bot * 2)) * 100
    
    return {
        'profit_neto_usdt': profit_neto_usdt,
        'profit_neto_pct': profit_neto_pct,
        'long_profit_usdt': long_profit,
        'short_profit_usdt': short_profit,
        'fees_usdt': fees_acumulados,
        'long_operaciones': long_operaciones,
        'short_operaciones': short_operaciones,
        'total_operaciones': long_operaciones + short_operaciones,
        'precio_salida': precio_salida,
        'razon_cierre': razon_cierre,
        'long_profit_hist': long_profit_hist,
        'short_profit_hist': short_profit_hist,
        'fees_hist': fees_hist,
        'precio_hist': precio_hist,
        'niveles': niveles,
        'spread': spread,
        'long_posiciones_finales': len(long_posiciones),
        'short_posiciones_finales': len(short_posiciones)
    }

# ============================================
# EJECUCIÓN PRINCIPAL
# ============================================
print("=" * 80)
print("🤖 SIMULADOR DUAL GRID BOT - FLUIDUSDT (BINANCE FUTURES)")
print("=" * 80)
print(f"\n⚙️  CONFIGURACIÓN:")
print(f"   Símbolo: FLUIDUSDT (Perpetual)")
print(f"   Rango: {rango_min} - {rango_max} USDT")
print(f"   Número de rejillas: {rejillas} ({rejillas+1} niveles)")
print(f"   Capital por bot: {capital_por_bot} USDT")
print(f"   Capital total: {capital_por_bot * 2} USDT")
print(f"   Apalancamiento: {apalancamiento}x")
print(f"   Fee maker/taker: {fee * 100}%")

# Descargar datos reales
print("\n" + "=" * 80)
df = descargar_velas_binance(symbol='FLUIDUSDT', interval='1m', limit=1500)

if df is not None:
    # Ejecutar simulación
    print("\n" + "=" * 80)
    print("🎯 EJECUTANDO SIMULACIÓN...")
    print("=" * 80)
    resultado = simular_dual_grid(df, rango_min, rango_max, rejillas, 
                                   capital_por_bot, apalancamiento, fee)
    
    # Mostrar resultados
    print("\n" + "=" * 80)
    print("📊 RESULTADOS DE LA SIMULACIÓN")
    print("=" * 80)
    
    print(f"\n💰 PROFIT NETO TOTAL: {resultado['profit_neto_usdt']:.4f} USDT ({resultado['profit_neto_pct']:.2f}%)")
    
    print(f"\n📈 BOT LONG:")
    print(f"   Profit bruto: {resultado['long_profit_usdt']:.4f} USDT")
    print(f"   Operaciones completadas: {resultado['long_operaciones']}")
    print(f"   Posiciones abiertas finales: {resultado['long_posiciones_finales']}")
    if capital_por_bot > 0:
        print(f"   ROI Long (bruto): {(resultado['long_profit_usdt'] / capital_por_bot) * 100:.2f}%")
    
    print(f"\n📉 BOT SHORT:")
    print(f"   Profit bruto: {resultado['short_profit_usdt']:.4f} USDT")
    print(f"   Operaciones completadas: {resultado['short_operaciones']}")
    print(f"   Posiciones abiertas finales: {resultado['short_posiciones_finales']}")
    if capital_por_bot > 0:
        print(f"   ROI Short (bruto): {(resultado['short_profit_usdt'] / capital_por_bot) * 100:.2f}%")
    
    print(f"\n💸 FEES:")
    print(f"   Fees totales: {resultado['fees_usdt']:.4f} USDT")
    print(f"   Total operaciones: {resultado['total_operaciones']}")
    if resultado['total_operaciones'] > 0:
        print(f"   Fee promedio/operación: {resultado['fees_usdt'] / resultado['total_operaciones']:.4f} USDT")
    
    if resultado['razon_cierre']:
        print(f"\n⚠️  ESTADO: {resultado['razon_cierre']}")
        print(f"   Precio de salida: {resultado['precio_salida']:.4f} USDT")
        if resultado['razon_cierre'] == "Ruptura ALCISTA":
            print(f"   🎯 LONG GANÓ (precio subió fuera del rango)")
            print(f"   ❌ SHORT PERDIÓ")
        else:
            print(f"   🎯 SHORT GANÓ (precio bajó fuera del rango)")
            print(f"   ❌ LONG PERDIÓ")
    else:
        print(f"\n✅ ESTADO: Operando dentro del rango")
    
    # ============================================
    # VISUALIZACIÓN
    # ============================================
    fig = plt.figure(figsize=(18, 12))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.25)
    
    ax1 = fig.add_subplot(gs[0, :])  # Precio (ocupa ambas columnas)
    ax2 = fig.add_subplot(gs[1, :])  # Profit acumulado
    ax3 = fig.add_subplot(gs[2, 0])  # Barras comparativas
    ax4 = fig.add_subplot(gs[2, 1])  # Tabla resumen
    
    # Gráfico 1: Precio con niveles de grid
    ax1.plot(df['timestamp'], df['close'], label='Precio FLUIDUSDT', linewidth=1.5, color='blue', alpha=0.8)
    ax1.axhline(rango_min, color='red', linestyle='--', linewidth=2, label=f'Límite inferior ({rango_min})')
    ax1.axhline(rango_max, color='green', linestyle='--', linewidth=2, label=f'Límite superior ({rango_max})')
    
    # Dibujar niveles de rejilla
    for i, nivel in enumerate(resultado['niveles']):
        ax1.axhline(nivel, color='gray', linestyle=':', linewidth=0.8, alpha=0.4)
    
    if resultado['precio_salida']:
        ax1.axhline(resultado['precio_salida'], color='orange', linestyle='-', linewidth=3, 
                   label=f'Precio salida ({resultado["precio_salida"]:.4f})')
    
    ax1.set_title(f'Evolución Precio FLUIDUSDT (1m) - {resultado["razon_cierre"] or "Dentro del rango"}', 
                 fontsize=14, fontweight='bold')
    ax1.set_xlabel('Fecha/Hora', fontsize=11)
    ax1.set_ylabel('Precio (USDT)', fontsize=11)
    ax1.legend(fontsize=9, loc='best')
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis='x', rotation=45)
    
    # Gráfico 2: Profit acumulado
    timestamps = df['timestamp'][:len(resultado['long_profit_hist'])]
    profit_total_bruto = np.array(resultado['long_profit_hist']) + np.array(resultado['short_profit_hist'])
    profit_total_neto = profit_total_bruto - np.array(resultado['fees_hist'])
    
    ax2.plot(timestamps, resultado['long_profit_hist'], label='Profit LONG', color='green', linewidth=2)
    ax2.plot(timestamps, resultado['short_profit_hist'], label='Profit SHORT', color='red', linewidth=2)
    ax2.plot(timestamps, profit_total_bruto, label='Profit TOTAL (bruto)', color='blue', linewidth=2, alpha=0.7)
    ax2.plot(timestamps, profit_total_neto, label='Profit TOTAL (neto)', color='purple', linewidth=2.5)
    ax2.axhline(0, color='black', linestyle='-', linewidth=0.8)
    
    ax2.set_title('Profit Acumulado (USDT)', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Fecha/Hora', fontsize=11)
    ax2.set_ylabel('Profit (USDT)', fontsize=11)
    ax2.legend(fontsize=9, loc='best')
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis='x', rotation=45)
    
    # Gráfico 3: Barras comparativas
    categories = ['LONG', 'SHORT', 'TOTAL\n(bruto)', 'TOTAL\n(neto)']
    valores = [
        resultado['long_profit_usdt'],
        resultado['short_profit_usdt'],
        resultado['long_profit_usdt'] + resultado['short_profit_usdt'],
        resultado['profit_neto_usdt']
    ]
    colores = ['green', 'red', 'blue', 'purple']
    
    bars = ax3.bar(categories, valores, color=colores, alpha=0.7, edgecolor='black', linewidth=1.5)
    ax3.axhline(0, color='black', linestyle='-', linewidth=1)
    ax3.set_title('Comparación de Profits (USDT)', fontsize=13, fontweight='bold')
    ax3.set_ylabel('Profit (USDT)', fontsize=11)
    ax3.grid(True, alpha=0.3, axis='y')
    
    for bar, valor in zip(bars, valores):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{valor:.2f}\n({(valor/(capital_por_bot*2))*100:.1f}%)',
                ha='center', va='bottom' if valor >= 0 else 'top', fontsize=9, fontweight='bold')
    
    # Tabla resumen
    ax4.axis('tight')
    ax4.axis('off')
    
    tabla_data = [
        ['PARÁMETRO', 'VALOR'],
        ['━━━━━━━━━━━━━━━━━', '━━━━━━━━━━━'],
        ['Capital Total', f'{capital_por_bot * 2} USDT'],
        ['Apalancamiento', f'{apalancamiento}x'],
        ['Rejillas', f'{rejillas}'],
        ['Spread/rejilla', f'{resultado["spread"]:.6f} USDT'],
        ['━━━━━━━━━━━━━━━━━', '━━━━━━━━━━━'],
        ['Operaciones LONG', f'{resultado["long_operaciones"]}'],
        ['Operaciones SHORT', f'{resultado["short_operaciones"]}'],
        ['Total Operaciones', f'{resultado["total_operaciones"]}'],
        ['━━━━━━━━━━━━━━━━━', '━━━━━━━━━━━'],
        ['Fees Totales', f'{resultado["fees_usdt"]:.4f} USDT'],
        ['Profit Neto', f'{resultado["profit_neto_usdt"]:.4f} USDT'],
        ['ROI Total', f'{resultado["profit_neto_pct"]:.2f}%']
    ]
    
    table = ax4.table(cellText=tabla_data, cellLoc='left', loc='center',
                     colWidths=[0.6, 0.4])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)
    
    for i in range(len(tabla_data)):
        if i == 0:
            for j in range(2):
                table[(i, j)].set_facecolor('#4CAF50')
                table[(i, j)].set_text_props(weight='bold', color='white')
        elif '━' in tabla_data[i][0]:
            for j in range(2):
                table[(i, j)].set_facecolor('#E0E0E0')
        else:
            table[(i, 0)].set_facecolor('#F5F5F5')
            table[(i, 1)].set_facecolor('#FFFFFF')
    
    ax4.set_title('Resumen de Configuración', fontsize=13, fontweight='bold', pad=20)
    
    plt.suptitle('ANÁLISIS DUAL GRID BOT - FLUIDUSDT', fontsize=16, fontweight='bold', y=0.995)
    plt.show()
    
    print("\n" + "=" * 80)
    print("✅ Simulación completada")
    print("=" * 80)
    
else:
    print("❌ No se pudieron descargar los datos")
    print("   Verifica tu conexión a internet y que FLUIDUSDT esté disponible en Binance Futures")