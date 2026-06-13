Work with GreenPrompt's power measurement layer (sysUsage.py, samplerMac.py).

Task: $ARGUMENTS

If no specific task is given, audit the current power measurement setup:

1. Detect the current platform:
   ```bash
   python3 -c "import platform; print(platform.system())"
   ```

2. On macOS:
   - Verify `powermetrics` is accessible: `which powermetrics`
   - Test a single sample: `sudo powermetrics --samplers cpu_power -n 1 -i 1000`
   - Read `samplerMac.py` and verify `PowerMonitor` can be instantiated
   - Check that `parse_powermetrics_output()` correctly extracts CPU/GPU/Combined power from the sample output

3. On Linux:
   - Check GPU availability: `nvidia-smi -L` (if NVIDIA GPU present)
   - Check RAPL availability: `ls /sys/class/powercap/intel-rapl/` 
   - Read `sysUsage.py` lines 68-105 — show the current stub and explain what needs to be implemented
   - Report what hardware-based measurement is currently possible on this system

4. On all platforms:
   - Test `get_system_info()`: run it and show the output
   - Test `has_gpu()` and `get_gpu_usage()`: run both and show results

Key files:
- `greenprompt/greenprompt/samplerMac.py` — PowerMonitor class (macOS only)
- `greenprompt/greenprompt/sysUsage.py` — OS-agnostic dispatch, parsing, system info

If the task in $ARGUMENTS is to implement Linux power measurement:
- Read `sysUsage.py` fully
- Implement `measure_power_linux()` using RAPL sysfs at `/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj` for CPU and `nvidia-smi --query-gpu=power.draw --format=csv,nounits,noheader` for GPU
- Follow the same return dict format as `measure_power_mac()`: keys cpu_power_w, gpu_power_w, combined_power_w, duration_sec, energy_wh, baseline_power_w, baseline_energy_wh
- Create `samplerLinux.py` mirroring the interface of `samplerMac.py` if continuous sampling is needed
- Uncomment the `measure_power_linux()` call in `measure_power_for_pid()`
