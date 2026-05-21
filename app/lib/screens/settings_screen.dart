import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../providers/chat_provider.dart';
import '../theme/app_theme.dart';
import 'parent_dashboard_screen.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late final TextEditingController _urlCtrl;
  bool _testing = false;
  String? _testResult;
  bool _testOk = false;

  @override
  void initState() {
    super.initState();
    final current = ref.read(chatProvider).serverUrl ?? '';
    _urlCtrl = TextEditingController(text: current);
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await ref.read(chatProvider.notifier).setServerUrl(_urlCtrl.text);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Server URL saved!'),
        backgroundColor: AppTheme.success,
        duration: Duration(seconds: 2),
      ),
    );
  }

  Future<void> _test() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) return;

    setState(() {
      _testing = true;
      _testResult = null;
    });

    try {
      final cleanUrl = url.endsWith('/') ? url.substring(0, url.length - 1) : url;
      final response = await http
          .get(Uri.parse('$cleanUrl/health'))
          .timeout(const Duration(seconds: 8));

      if (response.statusCode == 200) {
        setState(() {
          _testOk = true;
          _testResult = 'Connected! Parth server is online.';
        });
      } else {
        setState(() {
          _testOk = false;
          _testResult = 'Server responded with ${response.statusCode}.';
        });
      }
    } catch (_) {
      setState(() {
        _testOk = false;
        _testResult = 'Cannot reach server. Check the IP address and WiFi.';
      });
    } finally {
      setState(() => _testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(chatProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          // ── Server status banner ──────────────────────────────────────────
          _StatusBanner(usingLocal: state.usingLocalServer),
          const SizedBox(height: 24),

          // ── Server URL ────────────────────────────────────────────────────
          _SectionHeader(icon: Icons.wifi, title: 'Local AI Server'),
          const SizedBox(height: 8),
          const Text(
            'Run Parth\'s local AI on your Mac and enter the server address here so the app uses it instead of the cloud.',
            style: TextStyle(fontSize: 13, color: AppTheme.lightText, height: 1.5),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _urlCtrl,
            decoration: const InputDecoration(
              labelText: 'Server URL',
              hintText: 'http://10.245.254.147:8000',
              prefixIcon: Icon(Icons.dns_outlined, color: AppTheme.deepBlue),
              helperText: 'Mac\'s WiFi IP + port 8000',
            ),
            keyboardType: TextInputType.url,
            autocorrect: false,
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _testing ? null : _test,
                  icon: _testing
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.deepBlue),
                        )
                      : const Icon(Icons.wifi_find_outlined, size: 18),
                  label: Text(_testing ? 'Testing…' : 'Test Connection'),
                  style: OutlinedButton.styleFrom(foregroundColor: AppTheme.deepBlue),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _save,
                  icon: const Icon(Icons.save_outlined, size: 18),
                  label: const Text('Save'),
                ),
              ),
            ],
          ),
          if (_testResult != null) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: _testOk ? AppTheme.success.withOpacity(0.1) : Colors.red.shade50,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: _testOk ? AppTheme.success : Colors.red.shade200,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    _testOk ? Icons.check_circle_outline : Icons.error_outline,
                    color: _testOk ? AppTheme.success : Colors.red,
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _testResult!,
                      style: TextStyle(
                        fontSize: 13,
                        color: _testOk ? AppTheme.success : Colors.red,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 8),
          _QuickFillTile(
            label: 'Local WiFi (192.168.1.33)',
            url: 'http://192.168.1.33:8000',
            onTap: (url) {
              _urlCtrl.text = url;
              HapticFeedback.selectionClick();
            },
          ),
          _QuickFillTile(
            label: 'Internet tunnel (works anywhere)',
            url: 'https://improvement-harris-governmental-attacks.trycloudflare.com',
            onTap: (url) {
              _urlCtrl.text = url;
              HapticFeedback.selectionClick();
            },
          ),

          const SizedBox(height: 28),

          // ── How to start server ───────────────────────────────────────────
          _SectionHeader(icon: Icons.terminal, title: 'Start the Server'),
          const SizedBox(height: 8),
          _CodeBlock(
            'cd /Volumes/Seagate/Parth/server\n./start.sh',
          ),

          const SizedBox(height: 28),

          // ── Parent dashboard ──────────────────────────────────────────────
          _SectionHeader(icon: Icons.family_restroom_outlined, title: 'For Parents'),
          const SizedBox(height: 8),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.bar_chart_outlined, color: AppTheme.deepBlue),
            title: const Text('View Progress Report'),
            subtitle: const Text('See your child\'s learning activity and alerts'),
            trailing: const Icon(Icons.arrow_forward_ios, size: 14),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const ParentDashboardScreen()),
            ),
          ),

          const SizedBox(height: 28),

          // ── Clear local chat ──────────────────────────────────────────────
          _SectionHeader(icon: Icons.history, title: 'Chat Data'),
          const SizedBox(height: 8),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.delete_outline, color: Colors.red),
            title: const Text('Clear all chat history'),
            subtitle: const Text('Removes saved conversations from this device'),
            trailing: const Icon(Icons.arrow_forward_ios, size: 14),
            onTap: () => _confirmClear(context),
          ),

          const SizedBox(height: 40),
          const Center(
            child: Text(
              'Parth v1.0 · Made with ❤️ for every Indian child',
              style: TextStyle(fontSize: 11, color: AppTheme.lightText),
            ),
          ),
        ],
      ),
    );
  }

  void _confirmClear(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Clear Chat History'),
        content: const Text('This will delete all saved conversations. Are you sure?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              ref.read(chatProvider.notifier).clearChat();
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Chat history cleared.')),
              );
            },
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('Clear'),
          ),
        ],
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  final bool usingLocal;
  const _StatusBanner({required this.usingLocal});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: usingLocal ? AppTheme.success.withOpacity(0.1) : AppTheme.saffron.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: usingLocal ? AppTheme.success.withOpacity(0.4) : AppTheme.saffron.withOpacity(0.4),
        ),
      ),
      child: Row(
        children: [
          Icon(
            usingLocal ? Icons.router : Icons.cloud_outlined,
            color: usingLocal ? AppTheme.success : AppTheme.saffron,
            size: 22,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  usingLocal ? 'Using Local AI Server' : 'Using Cloud AI (Anthropic)',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                    color: usingLocal ? AppTheme.success : AppTheme.saffron,
                  ),
                ),
                Text(
                  usingLocal ? 'Free, private, works on LAN' : 'Requires API key & internet',
                  style: const TextStyle(fontSize: 12, color: AppTheme.lightText),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String title;
  const _SectionHeader({required this.icon, required this.title});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: AppTheme.deepBlue, size: 18),
        const SizedBox(width: 8),
        Text(
          title,
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.darkText),
        ),
      ],
    );
  }
}

class _CodeBlock extends StatelessWidget {
  final String code;
  const _CodeBlock(this.code);

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        code,
        style: const TextStyle(
          fontFamily: 'monospace',
          fontSize: 13,
          color: Color(0xFF00E676),
          height: 1.6,
        ),
      ),
    );
  }
}

class _QuickFillTile extends StatelessWidget {
  final String label;
  final String url;
  final ValueChanged<String> onTap;
  const _QuickFillTile({required this.label, required this.url, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => onTap(url),
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            const Icon(Icons.bolt, size: 16, color: AppTheme.saffron),
            const SizedBox(width: 6),
            Text(label, style: const TextStyle(fontSize: 13, color: AppTheme.saffron)),
          ],
        ),
      ),
    );
  }
}
