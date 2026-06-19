import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../theme/app_theme.dart';
import 'home_screen.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _nameController = TextEditingController();
  int _grade = 5;
  bool _loading = false;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _continue() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter your name!'),
          backgroundColor: AppTheme.saffron,
        ),
      );
      return;
    }

    setState(() => _loading = true);
    final prefs = await SharedPreferences.getInstance();
    // Generate a stable device-scoped learner ID on first launch.
    final existingId = prefs.getString('learner_id');
    if (existingId == null || existingId.isEmpty) {
      await prefs.setString('learner_id', const Uuid().v4());
    }
    await prefs.setString('user_name', name);
    await prefs.setInt('grade', _grade);
    await prefs.setBool('onboarded', true);

    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (_, __, ___) => const HomeScreen(),
        transitionsBuilder: (_, anim, __, child) =>
            FadeTransition(opacity: anim, child: child),
        transitionDuration: const Duration(milliseconds: 350),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [AppTheme.cream, Colors.white],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(28, 24, 28, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Center(child: Text('🙏', style: TextStyle(fontSize: 60))),
                const SizedBox(height: 20),
                const Center(
                  child: Text(
                    'Namaste!',
                    style: TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.deepBlue,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                const Center(
                  child: Text(
                    "I'm Parth, your personal AI mentor.\nLet's get to know each other!",
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 15, color: AppTheme.lightText, height: 1.55),
                  ),
                ),
                const SizedBox(height: 36),
                const Text(
                  "What's your name?",
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.darkText),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _nameController,
                  decoration: const InputDecoration(
                    hintText: 'Enter your name…',
                    prefixIcon: Icon(Icons.person_outline, color: AppTheme.deepBlue),
                  ),
                  textCapitalization: TextCapitalization.words,
                  autofocus: true,
                ),
                const SizedBox(height: 24),
                const Text(
                  'Which grade are you in?',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.darkText),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: List.generate(10, (i) {
                    final g = i + 1;
                    final selected = _grade == g;
                    return GestureDetector(
                      onTap: () => setState(() => _grade = g),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        width: 50,
                        height: 50,
                        decoration: BoxDecoration(
                          color: selected ? AppTheme.deepBlue : Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: selected ? AppTheme.deepBlue : Colors.grey.shade300,
                          ),
                          boxShadow: selected
                              ? [
                                  BoxShadow(
                                    color: AppTheme.deepBlue.withOpacity(0.3),
                                    blurRadius: 8,
                                    offset: const Offset(0, 2),
                                  ),
                                ]
                              : [],
                        ),
                        child: Center(
                          child: Text(
                            '$g',
                            style: TextStyle(
                              color: selected ? Colors.white : AppTheme.darkText,
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                            ),
                          ),
                        ),
                      ),
                    );
                  }),
                ),
                const Spacer(),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: _loading ? null : _continue,
                    child: _loading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                          )
                        : const Text('Start Learning! 🚀'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
