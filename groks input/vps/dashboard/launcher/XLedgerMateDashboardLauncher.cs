using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace XLedgerMateDashboardLauncher
{
    internal static class Program
    {
        private const string DefaultVpsIp = "188.245.50.229";
        private const int LocalPort = 8501;
        private const string Url = "http://localhost:8501/";

        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string keyPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                ".ssh",
                "hetzner_xledgermate");

            if (!File.Exists(keyPath))
            {
                MessageBox.Show(
                    "SSH key not found:\n" + keyPath + "\n\nSee groks input/FOR_AI_AND_FUTURE_SESSIONS.md",
                    "XLedgerMate Dashboard",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return;
            }

            string sshExe = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                "System32",
                "OpenSSH",
                "ssh.exe");

            if (!File.Exists(sshExe))
            {
                MessageBox.Show(
                    "OpenSSH not found at:\n" + sshExe + "\n\nEnable OpenSSH Client in Windows Optional Features.",
                    "XLedgerMate Dashboard",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return;
            }

            string args = string.Format(
                "-i \"{0}\" -N -L {1}:127.0.0.1:{1} root@{2}",
                keyPath,
                LocalPort,
                DefaultVpsIp);

            try
            {
                ProcessStartInfo startInfo = new ProcessStartInfo();
                startInfo.FileName = sshExe;
                startInfo.Arguments = args;
                startInfo.UseShellExecute = false;
                startInfo.CreateNoWindow = false;
                startInfo.WindowStyle = ProcessWindowStyle.Minimized;

                Process proc = Process.Start(startInfo);
                if (proc == null)
                {
                    MessageBox.Show("Could not start SSH tunnel.", "XLedgerMate Dashboard",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }

                Thread.Sleep(2500);

                try
                {
                    ProcessStartInfo browser = new ProcessStartInfo();
                    browser.FileName = Url;
                    browser.UseShellExecute = true;
                    Process.Start(browser);
                }
                catch
                {
                }

                MessageBox.Show(
                    "Dashboard tunnel is running.\n\n" +
                    "Browser: " + Url + "\n" +
                    "VPS: " + DefaultVpsIp + "\n\n" +
                    "Keep the small SSH window open. Close it to stop the tunnel.\n\n" +
                    "The bot on Hetzner keeps running if you close this message.",
                    "XLedgerMate Dashboard",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Failed to start tunnel:\n" + ex.Message,
                    "XLedgerMate Dashboard",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}