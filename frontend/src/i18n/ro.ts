/**
 * The Romanian texts. Typed as Dictionary: the same keys as en.ts, the same
 * kind of entry (text or plural) for each, or the build fails.
 *
 * Written to read naturally, not word for word: short, informal (tu), as
 * the app talks to people at the gym.
 */
import type { Dictionary } from './i18n'

export const ro: Dictionary = {
  'app.tagline': 'Antrenament și alimentație, într-un singur loc.',
  'app.loading': 'Se încarcă…',
  'app.tryAgain': 'Încearcă din nou',
  'app.cannotReach': 'Serverul nu răspunde',

  'nav.today': 'Azi',
  'nav.foods': 'Alimente',
  'nav.workouts': 'Antrenamente',
  'nav.programs': 'Programe',
  'nav.profile': 'Profil',
  'nav.logOut': 'Ieși',

  'auth.signUpTitle': 'Fă-ți un cont',
  'auth.logInTitle': 'Bine ai revenit',
  'auth.email': 'Email',
  'auth.password': 'Parolă',
  'auth.wait': 'O clipă…',
  'auth.signUp': 'Creează contul',
  'auth.logIn': 'Intră',
  'auth.toLogIn': 'Ai deja cont? Intră',
  'auth.toSignUp': 'Ești nou? Fă-ți un cont',

  'profile.title': 'Bine ai venit!',
  'profile.email': 'Email',
  'profile.memberSince': 'Membru din',
  'profile.crewNumber': 'Nr. în echipaj',
  'profile.weightsIn': 'Greutăți în',
  'profile.kilograms': 'Kilograme (kg)',
  'profile.pounds': 'Livre (lb)',
  'profile.unitNote':
    'Se salvează pe acest dispozitiv. Greutățile rămân stocate în kilograme, orice ai alege.',
  'profile.language': 'Limba',
  'profile.languageAuto': 'Ca în browser ({language})',
  'profile.languageNote':
    'Se salvează pe acest dispozitiv. Unele mesaje de la server pot apărea în engleză.',
}
