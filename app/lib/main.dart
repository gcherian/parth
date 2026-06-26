import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'screens/splash_screen.dart';
import 'theme/app_theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await Hive.openBox('messages');
  await Hive.openBox('settings');
  runApp(const ProviderScope(child: ParthApp()));
}

class ParthApp extends StatelessWidget {
  const ParthApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Parth',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const SplashScreen(),
    );
  }
}
