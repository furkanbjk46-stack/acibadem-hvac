# belimo_modbus_test.py
# AHU-03 Isitma Belimo vanasini Modbus TCP ile test eder.
# Gereksinim: pip install pymodbus

from pymodbus.client import ModbusTcpClient

IP      = "192.168.0.35"
PORT    = 502
SLAVE   = 1

def test():
    print(f"\nBelimo Modbus TCP baglantisi: {IP}:{PORT} (slave={SLAVE})\n")
    client = ModbusTcpClient(IP, port=PORT)
    if not client.connect():
        print("[HATA] Baglanamadi!")
        return

    print("[OK] Baglandi.\n")

    # Holding registers oku (0-30 arasi)
    print("=== Holding Registers (0-30) ===")
    rr = client.read_holding_registers(0, count=30, slave=SLAVE)
    if not rr.isError():
        for i, val in enumerate(rr.registers):
            print(f"  HR[{i:2d}] = {val:6d}  ({val/10:.1f}%  /  {val/100:.2f})")
    else:
        print(f"  HATA: {rr}")

    print()

    # Input registers oku (0-20 arasi)
    print("=== Input Registers (0-20) ===")
    ir = client.read_input_registers(0, count=20, slave=SLAVE)
    if not ir.isError():
        for i, val in enumerate(ir.registers):
            print(f"  IR[{i:2d}] = {val:6d}  ({val/10:.1f}  /  {val/100:.2f})")
    else:
        print(f"  HATA: {ir}")

    client.close()
    print("\nTest tamamlandi.")

if __name__ == "__main__":
    try:
        test()
    except ModuleNotFoundError:
        print("\n[HATA] pymodbus yuklu degil!")
        print("Komut satirinda su komutu calistirin:")
        print("  pip install pymodbus")
    except Exception as e:
        print(f"\n[HATA] {e}")
    finally:
        input("\nCikmak icin Enter'a basin...")
