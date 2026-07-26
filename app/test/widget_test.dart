import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:parth/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('ParthApp shows the splash screen', (tester) async {
    SharedPreferences.setMockInitialValues({});

    await tester.pumpWidget(const ProviderScope(child: ParthApp()));
    await tester.pump();

    expect(find.text('Parth'), findsOneWidget);
    expect(find.text('पार्थ • Your AI Mentor'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 2400));
    await tester.pumpAndSettle();

    expect(find.text("What's your name?"), findsOneWidget);
  });
}
