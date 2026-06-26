import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  // Primary palette — vibrant, playful, culturally warm
  static const Color violet     = Color(0xFF6C3EB8);   // deep purple-violet (primary)
  static const Color violetLight= Color(0xFF8B5CF6);   // lighter purple for gradients
  static const Color mango      = Color(0xFFFF9500);   // warm saffron-mango (accent)
  static const Color mint       = Color(0xFF00C896);   // fresh mint (success / correct)
  static const Color coral      = Color(0xFFFF5C6A);   // coral (alerts / wrong)
  static const Color sky        = Color(0xFF38BEFF);   // sky blue (secondary accent)
  static const Color sunYellow  = Color(0xFFFFD60A);   // star / achievement yellow

  // Neutrals
  static const Color darkText   = Color(0xFF1C1033);
  static const Color bodyText   = Color(0xFF4B3F72);
  static const Color lightText  = Color(0xFF9E8FC0);
  static const Color bgWarm     = Color(0xFFF7F4FF);   // very light lavender bg
  static const Color surface    = Color(0xFFFFFFFF);
  static const Color cardBg     = Color(0xFFF0EBF8);

  // Legacy aliases (used in existing widgets)
  static const Color saffron    = mango;
  static const Color deepBlue   = violet;
  static const Color cream      = bgWarm;
  static const Color success    = mint;

  // Gradient helpers
  static const LinearGradient heroGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [violet, Color(0xFF9B59D0)],
  );

  static const LinearGradient mangoGradient = LinearGradient(
    colors: [mango, Color(0xFFFF6B00)],
  );

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: violet,
          primary: violet,
          secondary: mango,
          tertiary: mint,
          surface: bgWarm,
        ),
        scaffoldBackgroundColor: bgWarm,
        textTheme: GoogleFonts.nunitoTextTheme().copyWith(
          displayLarge: GoogleFonts.nunito(fontWeight: FontWeight.w900),
          displayMedium: GoogleFonts.nunito(fontWeight: FontWeight.w900),
          headlineLarge: GoogleFonts.nunito(fontWeight: FontWeight.w800),
          headlineMedium: GoogleFonts.nunito(fontWeight: FontWeight.w700),
          titleLarge: GoogleFonts.nunito(fontWeight: FontWeight.w700),
          titleMedium: GoogleFonts.nunito(fontWeight: FontWeight.w600),
          bodyLarge: GoogleFonts.nunito(fontWeight: FontWeight.w500),
          bodyMedium: GoogleFonts.nunito(fontWeight: FontWeight.w400),
          labelLarge: GoogleFonts.nunito(fontWeight: FontWeight.w700),
        ),
        appBarTheme: AppBarTheme(
          backgroundColor: violet,
          foregroundColor: Colors.white,
          elevation: 0,
          centerTitle: false,
          titleTextStyle: GoogleFonts.nunito(
            color: Colors.white,
            fontSize: 22,
            fontWeight: FontWeight.w800,
          ),
          iconTheme: const IconThemeData(color: Colors.white),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: mango,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
            elevation: 3,
            shadowColor: mango.withOpacity(0.4),
            textStyle: GoogleFonts.nunito(fontSize: 17, fontWeight: FontWeight.w800),
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: violet,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            textStyle: GoogleFonts.nunito(fontSize: 16, fontWeight: FontWeight.w700),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(18)),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: const BorderSide(color: Color(0xFFD8CEED), width: 1.5),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: const BorderSide(color: violet, width: 2.5),
          ),
          filled: true,
          fillColor: Colors.white,
          contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          hintStyle: GoogleFonts.nunito(color: lightText, fontWeight: FontWeight.w500),
        ),
        cardTheme: CardThemeData(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          shadowColor: violet.withOpacity(0.08),
          margin: EdgeInsets.zero,
        ),
        chipTheme: ChipThemeData(
          backgroundColor: cardBg,
          selectedColor: violet,
          labelStyle: GoogleFonts.nunito(fontWeight: FontWeight.w600),
          shape: const StadiumBorder(),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        ),
        navigationBarTheme: NavigationBarThemeData(
          backgroundColor: Colors.white,
          elevation: 8,
          shadowColor: violet.withOpacity(0.1),
          indicatorColor: violet.withOpacity(0.15),
          labelTextStyle: WidgetStateProperty.all(
            GoogleFonts.nunito(fontSize: 12, fontWeight: FontWeight.w700),
          ),
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: mango,
          foregroundColor: Colors.white,
          elevation: 6,
          shape: StadiumBorder(),
        ),
      );
}
