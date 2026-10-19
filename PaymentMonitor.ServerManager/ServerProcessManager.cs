using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Net.Sockets;

namespace PaymentMonitor.ServerManager;

public class ServerProcessManager
{
    private Process? _process;
    private readonly AppSettings _settings;

    public event Action<string>? OnStatusChanged;
    public event Action<string>? OnLog;

    public bool IsRunning => _process != null && !_process.HasExited;

    public ServerProcessManager(AppSettings settings) => _settings = settings;

    public async Task<bool> StartAsync()
    {
        if (!IsRunning && await IsServerRespondingAsync()) return true;
        if (IsRunning) return true;

        var exePath = Path.Combine(_settings.ServerFolder, "PaymentMonitor.Server.exe");
        if (!File.Exists(exePath))
        {
            OnStatusChanged?.Invoke("✗ Server exe not found");
            return false;
        }

        try
        {
            OnStatusChanged?.Invoke("⏳ Starting...");
            var psi = new ProcessStartInfo
            {
                FileName = exePath,
                WorkingDirectory = _settings.ServerFolder,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };

            _process = new Process { StartInfo = psi };
            _process.OutputDataReceived += (s, e) => { if (!string.IsNullOrEmpty(e.Data)) OnLog?.Invoke(e.Data); };
            _process.ErrorDataReceived += (s, e) => { if (!string.IsNullOrEmpty(e.Data)) OnLog?.Invoke($"[ERROR] {e.Data}"); };

            _process.Start();
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();

            for (int i = 0; i < 15; i++)
            {
                await Task.Delay(500);
                if (await IsServerRespondingAsync())
                {
                    OnStatusChanged?.Invoke($"🟢 Running on {_settings.Port}");
                    return true;
                }
                if (_process.HasExited)
                {
                    OnStatusChanged?.Invoke("✗ Server stopped");
                    return false;
                }
            }
            return false;
        }
        catch (Exception ex)
        {
            OnStatusChanged?.Invoke($"✗ Error: {ex.Message}");
            return false;
        }
    }

    public async Task StopAsync()
    {
        if (_process != null && !_process.HasExited)
        {
            try
            {
                OnStatusChanged?.Invoke("⏳ Stopping...");
                _process.Kill(entireProcessTree: true);
                await _process.WaitForExitAsync();
                _process.Dispose();
                _process = null;
            }
            catch { }
        }
        OnStatusChanged?.Invoke("⚫ Stopped");
    }

    public async Task<int> KillProcessOnPortAsync()
    {
        int killed = 0;
        try
        {
            var psi = new ProcessStartInfo("netstat", "-ano -p tcp")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true
            };
            using var p = Process.Start(psi)!;
            var output = await p.StandardOutput.ReadToEndAsync();
            await p.WaitForExitAsync();

            foreach (var line in output.Split('\n'))
            {
                var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length < 5) continue;
                if (!parts[1].EndsWith(":" + _settings.Port)) continue;
                if (!parts[2].EndsWith(":0")) continue;
                if (!int.TryParse(parts[4].Trim(), out var pid)) continue;

                try
                {
                    var proc = Process.GetProcessById(pid);
                    proc.Kill(entireProcessTree: true);
                    await proc.WaitForExitAsync();
                    killed++;
                }
                catch { }
            }
        }
        catch { }
        return killed;
    }

    public async Task<bool> IsServerRespondingAsync()
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            return (await http.GetAsync($"http://127.0.0.1:{_settings.Port}/ping")).IsSuccessStatusCode;
        }
        catch { return false; }
    }

    public string GetLocalIp()
    {
        try
        {
            using var socket = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
            socket.Connect("8.8.8.8", 80);
            return ((System.Net.IPEndPoint)socket.LocalEndPoint!).Address.ToString();
        }
        catch { return "127.0.0.1"; }
    }
}