namespace PaymentMonitor.ServerManager;

public class AppSettings
{
    public string ServerFolder { get; set; } = "";
    public string PythonPath { get; set; } = "";
    public int Port { get; set; } = 5000;
    public bool AutoStart { get; set; } = true;
}
