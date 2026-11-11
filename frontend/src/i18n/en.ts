/**
 * The English texts, the source of every key. Romanian (ro.ts) must have
 * exactly the same keys: a missing or extra one fails the build.
 *
 * {name} is a parameter. An entry with forms (one, other...) is a plural:
 * the form comes from Intl.PluralRules for the count.
 */
import type { Plural } from './plural'

export const en = {
  'app.tagline': 'Train your Haki. Track your fuel.',
  'app.loading': 'Loading…',
  'app.tryAgain': 'Try again',
  'app.cannotReach': 'Cannot reach the server',

  'nav.today': 'Today',
  'nav.foods': 'Foods',
  'nav.workouts': 'Workouts',
  'nav.programs': 'Programs',
  'nav.profile': 'Profile',
  'nav.logOut': 'Log out',

  'auth.signUpTitle': 'Create your account',
  'auth.logInTitle': 'Welcome back',
  'auth.email': 'Email',
  'auth.password': 'Password',
  'auth.wait': 'Please wait…',
  'auth.signUp': 'Sign up',
  'auth.logIn': 'Log in',
  'auth.toLogIn': 'Already have an account? Log in',
  'auth.toSignUp': 'New here? Create an account',

  'profile.title': 'Welcome aboard!',
  'profile.email': 'Email',
  'profile.memberSince': 'Member since',
  'profile.crewNumber': 'Crew number',
  'profile.weightsIn': 'Weights in',
  'profile.kilograms': 'Kilograms (kg)',
  'profile.pounds': 'Pounds (lb)',
  'profile.unitNote':
    'Saved on this device. Your weights are stored in kilograms whatever you choose here.',
  'profile.language': 'Language',
  'profile.languageAuto': 'Same as the browser ({language})',
  'profile.languageNote':
    'Saved on this device. Some messages from the server may still be in English.',
} satisfies Record<string, string | Plural>
