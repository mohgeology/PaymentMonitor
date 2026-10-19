using System.Windows;
using System.IO;
using Microsoft.Win32;

namespace PaymentMonitor.ServerManager;

public partial class SettingsWindow : Window
{
    public AppSettings? SavedSettings { get; private set; }

    public SettingsWindow(AppSettings current)
    {
        InitializeComponent();
        ServerFolderBox.Text = current.ServerFolder;
        PythonPathBox.Text = current.PythonPath;
        PortBox.Text = current.Port.ToString();
    }

    private void BrowseServerFolder_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = "اختر مجلد السيرفر (يحتوي main.py)"
        };
        if (dialog.ShowDialog() == true)
        {
            ServerFolderBox.Text = dialog.FolderName;
        }
    }

    private void BrowsePythonPath_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = "اختر pythonw.exe",
            Filter = "Python|python*.exe|كل الملفات|*.*"
        };
        if (dialog.ShowDialog() == true)
        {
            PythonPathBox.Text = dialog.FileName;
        }
    }

    private void SaveBtn_Click(object sender, RoutedEventArgs e)
    {
        var folder = ServerFolderBox.Text?.Trim() ?? "";
        var python = PythonPathBox.Text?.Trim() ?? "";
        var portText = PortBox.Text?.Trim() ?? "5000";

        if (string.IsNullOrEmpty(folder) || !System.IO.Directory.Exists(folder))
        {
            System.Windows.MessageBox.Show("مجلد السيرفر غير صحيح", "خطأ", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        if (string.IsNullOrEmpty(python) || !System.IO.File.Exists(python))
        {
            System.Windows.MessageBox.Show("مسار Python غير صحيح", "خطأ", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        if (!int.TryParse(portText, out var port) || port < 1 || port > 65535)
        {
            System.Windows.MessageBox.Show("المنفذ غير صحيح (1-65535)", "خطأ", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        SavedSettings = new AppSettings
        {
            ServerFolder = folder,
            PythonPath = python,
            Port = port,
            AutoStart = true
        };

        DialogResult = true;
        Close();
    }

    private void CloseBtn_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
