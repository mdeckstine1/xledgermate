using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace XLedgerMateFullGuiLauncher
{
    internal static class Program
    {
        private const string DefaultVpsIp = "188.245.50.229";
        private const int LocalPort = 8502;
        private const string Url = "http://localhost:8502/";

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
                    "SSH key not found:\n" + keyPath,
                    "XLedgerMate Full GUI",
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
                    "OpenSSH not found. Enable OpenSSH Client in Windows Optional Features.",
                    "XLedgerMate Full GUI",
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
                    MessageBox.Show("Could not start SSH tunnel.", "XLedgerMate Full GUI",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }

                Thread.Sleep(3000);

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
                    "Full trading GUI tunnel is running.\n\n" +
                    "Browser: " + Url + "\n" +
                    "(Same interface as local repo — controls engine on VPS.)\n\n" +
                    "Keep the minimized SSH window open.\n\n" +
                    "Light monitoring dashboard is still on http://localhost:8501",
                    "XLedgerMate Full GUI",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Failed to start tunnel:\n" + ex.Message,
                    "XLedgerMate Full GUI",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}