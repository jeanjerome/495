# Java / Kotlin test libraries, by role

- Date: 2026-09-13
- Fills: `docs/test-libraries.md`, section Java / Kotlin
- Rule applied: `docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md`

One recommended library per role of the Java / Kotlin table (runner, bdd, property, mutation,
coverage, architecture, static, security, contract, performance, doubles), chosen among the
candidates a JVM project would reach for. Where Kotlin has a library of its own that the Java
entry cannot replace, the cell holds a second entry with its condition. Every fact below was
measured on the date above; nothing is taken from memory alone.

## Method

1. **Candidates.** For each role, the libraries and build plugins the ecosystem uses, in Java
   and in Kotlin.
2. **Maintenance and terms.** Latest release and date, read from Maven Central's repository
   metadata (`maven-metadata.xml` under `repo1.maven.org`; the search index was a year behind
   on the day). A library whose last release is older than three years is not recommended,
   with one stated exception below.
3. **Smoke run, Java.** A Maven project (OpenJDK 25.0.4, Maven 3.9.9, `release` 21) with a
   `domain` package (`clamp`, `add`, a class calling `infra`), an `infra` package using `MD5`
   and `Runtime.exec` with a variable, and a class with an unused local, an empty catch and a
   duplicated method; each tool run through its Maven plugin.
4. **Smoke run, Kotlin.** A Gradle project (Gradle 9.7.1 from the official archive, Kotlin
   2.4.20, then 2.2.21 for one retry) with the same functions, each tool run through its Gradle
   plugin.

## Facts measured

### Releases, as read on Maven Central

| Artifact | Version | Released |
|---|---|---|
| org.junit.jupiter:junit-jupiter | 6.1.3 | 2026-08-07 |
| io.kotest:kotest-runner-junit5, kotest-property | 6.2.5 | 2026-09-10 |
| org.testng:testng | 7.12.0 | 2026-01-22 |
| org.spockframework:spock-core | 2.4-groovy-5.0 | 2025-12-11 |
| io.cucumber:cucumber-java, cucumber-junit-platform-engine | 7.34.8 | 2026-09-06 |
| net.jqwik:jqwik | 1.10.1 | 2026-05-29 |
| org.quicktheories:quicktheories | 0.26 | 2019-03-06 |
| org.pitest:pitest-maven | 1.30.0 | 2026-08-27 |
| org.pitest:pitest-junit5-plugin | 1.2.3 | 2025-05-20 |
| org.jacoco:jacoco-maven-plugin | 0.8.15 | 2026-06-05 |
| org.jetbrains.kotlinx:kover-gradle-plugin | 0.9.9 | 2026-07-17 |
| com.tngtech.archunit:archunit-junit5 | 1.5.0 | 2026-08-04 |
| com.lemonappdev:konsist | 0.17.3 | 2024-12-08 |
| com.puppycrawl.tools:checkstyle | 14.1.0 | 2026-08-30 |
| net.sourceforge.pmd:pmd-java | 7.27.0 | 2026-08-28 |
| org.apache.maven.plugins:maven-pmd-plugin | 3.28.0 (bundles PMD 7.17.0) | 2025-10-10 |
| io.gitlab.arturbosch.detekt:detekt-cli | 1.23.8 | 2025-02-21 |
| com.pinterest.ktlint:ktlint-cli | 1.8.0 | 2025-12-15 |
| com.google.errorprone:error_prone_core | 2.50.0 | 2026-06-10 |
| com.diffplug.spotless:spotless-maven-plugin | 3.10.2 | 2026-09-04 |
| com.github.spotbugs:spotbugs | 4.10.4 | 2026-08-20 |
| com.h3xstream.findsecbugs:findsecbugs-plugin | 1.14.0 | 2025-04-20 |
| org.owasp:dependency-check-maven | 13.0.0 | 2026-08-03 |
| com.code-intelligence:jazzer-junit | 0.30.0 | 2026-02-24 |
| com.atlassian.oai:swagger-request-validator-core | 3.0.0 | 2026-05-21 |
| org.springframework.cloud:spring-cloud-contract-verifier | 5.0.3 | 2026-06-11 |
| au.com.dius.pact.consumer:junit5 | 4.7.5 | 2026-08-10 |
| org.openapi4j:openapi-operation-validator | 1.0.7 | 2021-03-08 |
| io.rest-assured:rest-assured | 6.0.1 | 2026-07-10 |
| org.openjdk.jmh:jmh-core | 1.37 | 2023-08-03 |
| org.jetbrains.kotlinx:kotlinx-benchmark-runtime | 0.5.0 | 2026-09-01 |
| org.mockito:mockito-core | 5.23.0 | 2026-03-11 |
| io.mockk:mockk | 1.14.11 | 2026-05-29 |
| org.wiremock:wiremock | 4.0.0-beta.38 | 2026-07-02 |
| org.jetbrains.kotlin:kotlin-stdlib | 2.4.20 | 2026-09-07 |

JMH's last release is three years and one month old; the openjdk/jmh repository was
committed to on 2026-07-14, JMH is the JDK project's own harness, and kotlinx-benchmark 0.5.0
(2026-09-01) wraps it. The study takes it as the exception to the release rule.

### Smoke run, Maven

| Tool | What ran | Observed |
|---|---|---|
| JUnit Jupiter 6.1.3, surefire 3.6.0 | `mvn test` | 8 tests in 5 classes, all passing, one XML report per class under `target/surefire-reports/` |
| jqwik 1.10.1 | `@Property boolean staysWithinBounds(@ForAll int x, @ForAll @IntRange(...) int lo, ...)` | `tries = 1000`, reported with the JUnit tests |
| cucumber-java and cucumber-junit-platform-engine 7.34.8 | a `@Suite @IncludeEngines("cucumber")` class, one feature under `src/test/resources`, three steps | the scenario printed with ✔ per step, one JUnit test |
| ArchUnit 1.5.0 | `noClasses().that().resideInAPackage("..domain..").should().dependOnClassesThat().resideInAPackage("..infra..")` | with `domain` reading a `public static final int` of `infra`, no violation: javac inlines the constant and the bytecode holds no dependency; with a method call, the violation is reported with the caller, the callee and the line |
| Mockito 5.23.0 | `mock(IntSupplier.class)`, `when(...).thenReturn(7)`, `verify` | passes |
| swagger-request-validator-core 3.0.0 | `OpenApiInteractionValidator` over an inline description, a response missing the required `name` | `hasErrors()`, the first message names `name` |
| JaCoCo 0.8.15 | `prepare-agent` and `report` bound to `test` | `target/site/jacoco/jacoco.xml` with per-line `ci` counts (`Math.java` line 5: 12, `Bad.java` line 3: 0), the format diff-cover reads |
| PIT 1.30.0 with pitest-junit5-plugin 1.2.3 | `mvn org.pitest:pitest-maven:mutationCoverage` on `sample.domain.*` with `MathTest` | 10 mutations: 5 killed, 4 survived (the two boundary and two primitive-return mutants of `clamp` line 5), 1 without coverage; `mutations.xml` under `target/pit-reports/` |
| Checkstyle 14.1.0 | `checkstyle:check` with `google_checks.xml` | 36 violations, build failure |
| PMD 7.17.0 | `pmd:check` on a class with an unused local and an empty catch; `pmd:cpd-check -DminimumTokens=20` on a duplicated method | 2 violations, build failure; 1 duplication, build failure |
| SpotBugs 4.10.4 with findsecbugs 1.14.0 | `spotbugs:check` | `COMMAND_INJECTION` (Medium) on `Runtime.exec("ls " + cmd)`, `WEAK_MESSAGE_DIGEST_MD5` (High), build failure with 2 bugs; `target/spotbugsXml.xml` |
| OWASP dependency-check 13.0.0 | `dependency-check:check` without an NVD key | "Invalid API Key, length of 0": the NVD data feed requires an API key (free, from NIST) since the 2023 feed change |
| JMH 1.37 | `org.openjdk.jmh.Main sample.ClampBench -rf json` | "Unable to find the resource: /META-INF/BenchmarkList" until annotation processing is on (`-Dmaven.compiler.proc=full`: JDK 23 and later default to `-proc:none`); then `ClampBench.clamp avgt 0.273 ns/op`, JSON result |

### Smoke run, Gradle, Kotlin

| Tool | What ran | Observed |
|---|---|---|
| kotest 6.2.5 (runner and property) | a `BehaviorSpec` with `given`/`when`/`then` blocks and a `forAll(Arb.int(), ...)` property | 3 tests passing; the scenario is code, not a feature file |
| MockK 1.14.11 | `mockk<Clock>()`, `every { c.now() } returns 7` | passes |
| Konsist 0.17.3 | `Konsist.scopeFromProject().files.withPackage("sample.domain..").assertFalse { ... }` | `KoInternalException: Project directory not found`, under Kotlin 2.4.20 and 2.2.21, with a `.git` directory and a `gradlew` file present; not run to a verdict |
| Kover 0.9.9 | `koverXmlReport` | `build/reports/kover/report.xml` with per-line `ci` counts (`Math.kt` line 5: 11, lines 7 and 9: 0) |
| detekt 1.23.8 | `detekt` | 3 weighted issues (`MayBeConst` among them), build failure |
| ktlint 1.x through org.jlleitschuh.gradle.ktlint 13.1.0 | `ktlintCheck` | `standard:function-signature` and `standard:if-else-wrapping` findings in `build/reports/ktlint/`, build failure |

## Decisions, by role

| Role | Recommended | Condition | Why this one | Set aside |
|---|---|---|---|---|
| runner | junit-jupiter | default | JUnit 6, the platform every other entry runs on (cucumber's engine, jqwik, ArchUnit's junit5 support, PIT's junit5 plugin) | testng, spock: runners of their own; a project that has one keeps it, the runner is never a gap |
| runner | kotest | the project is written in Kotlin | the Kotlin runner with its own specs and property module, on the JUnit platform | |
| bdd | cucumber-jvm | | `.feature` files the requester reads, steps as annotated methods, one `@Suite` class runs them on the JUnit platform; the same for Kotlin | kotest's `BehaviorSpec`: given/when/then in code, no feature file |
| property | jqwik | default | on the JUnit platform, `@Property` with `@ForAll` and constraints, shrinking, 1000 tries by default | quicktheories: last release 2019-03 |
| property | kotest-property | the project runs kotest | `forAll` with `Arb` generators inside the kotest specs, measured | |
| mutation | pitest | | the JVM mutation tester, bytecode mutators for Java and Kotlin, `mutations.xml`; killed 5 of 9 covered mutants on the sample and named the four survivors | none |
| coverage | jacoco | default | the JVM coverage agent, XML with per-line counts, which diff-cover reads for the changed lines | |
| coverage | kover | the project is written in Kotlin and built with Gradle | JetBrains' Kotlin-aware coverage over the same agent, XML with per-line counts, measured | |
| architecture | archunit | | rules over the bytecode dependencies as JUnit tests, the violation names caller, callee and line; note that a compile-time constant is inlined and leaves no dependency to see | konsist: `Project directory not found` on the smoke run, not run to a verdict |
| static | checkstyle, with PMD | default | checkstyle for the style rules and formatting, PMD for complexity and its CPD for duplication, both as Maven and Gradle plugins with a build failure on violations | error-prone: compiler-time bug patterns, a complement; spotless: a formatter driver |
| static | detekt, with ktlint | the project is written in Kotlin | detekt for the Kotlin rules and complexity, ktlint for formatting, measured through their Gradle plugins | |
| security | spotbugs (findsecbugs), OWASP dependency-check | | findsecbugs adds the security detectors to SpotBugs (command injection and weak digest found on the sample); dependency-check reads the NVD, with an API key the requester obtains from NIST | jazzer-junit: JVM fuzzing, the table has no fuzzing row |
| contract | swagger-request-validator | | validates a request and response pair against the OpenAPI description in-process, whatever the HTTP framework (adapters for RestAssured, MockMvc, WireMock, Spring) | spring-cloud-contract: Spring only; pact-jvm: consumer-driven contracts between services, a different question; openapi4j: last release 2021-03 |
| performance | jmh | | the JDK's own harness, statistics per benchmark, JSON results; needs annotation processing on (JDK 23 and later default to `-proc:none`) | kotlinx-benchmark: wraps JMH for Kotlin multiplatform, named in the notes |
| doubles | mockito | default | the JVM mocking library; `mockito-inline` is the default since 5, so final classes mock too | wiremock: HTTP doubles, a complement |
| doubles | mockk | the project is written in Kotlin | Kotlin's mocking library, coroutines and `object`s included, measured | |

## Notes carried into the catalogue

- OWASP dependency-check needs an NVD API key; without it the update fails.
- JMH needs annotation processing enabled on JDK 23 and later.
- ArchUnit sees no dependency through an inlined compile-time constant.
- Konsist 0.17.3 did not find the project directory under Gradle 9.7.

## What a profile can detect

Dependencies are the `artifactId`s of `pom.xml`, the artifact names and plugin ids of
`build.gradle` and `build.gradle.kts` (root and one level down) and of
`gradle/libs.versions.toml`.

| Role | Marker of the recommended tool |
|---|---|
| runner | `junit-jupiter`, `junit-jupiter-api`, `junit-bom`, `kotlin-test-junit5` (JUnit); `kotest-runner-junit5` (kotest); `testng`; `spock-core` |
| bdd | `cucumber-java`, `cucumber-junit-platform-engine`, `cucumber-junit`; `.feature` files under `src/test` |
| property | `jqwik`; `kotest-property`; `quicktheories` |
| mutation | `pitest-maven`, the `info.solidsoft.pitest` Gradle plugin, `pitest` in a CI file |
| coverage | `jacoco-maven-plugin`, the `jacoco` Gradle plugin; `kover-maven-plugin`, the `org.jetbrains.kotlinx.kover` Gradle plugin |
| architecture | `archunit-junit5`, `archunit`; `konsist` |
| static | `maven-checkstyle-plugin`, the `checkstyle` Gradle plugin, `checkstyle.xml`, `config/checkstyle/`; `maven-pmd-plugin`, the `pmd` Gradle plugin, `config/pmd/`; the `io.gitlab.arturbosch.detekt` plugin, `detekt.yml`, `config/detekt/`; the `org.jlleitschuh.gradle.ktlint` plugin, `ktlint-cli`, `ktlint-maven-plugin`, `ktlint` in a CI file |
| security | `spotbugs-maven-plugin`, the `com.github.spotbugs` Gradle plugin, `spotbugs-exclude.xml`; `dependency-check-maven`, the `org.owasp.dependencycheck` Gradle plugin, `dependency-check` in a CI file |
| contract | `swagger-request-validator` in a manifest; `spring-cloud-contract`; `au.com.dius.pact` |
| performance | `jmh-core`, the `me.champeau.jmh` Gradle plugin; `kotlinx-benchmark` |
| doubles | `mockito-core`, `mockito` in a manifest; `mockk`; `wiremock` |

The Kotlin condition holds when `src/main/kotlin` exists, `build.gradle.kts` applies
`kotlin(` or `org.jetbrains.kotlin`, or `pom.xml` declares `kotlin-maven-plugin`.

## Follow-ups

- A fuzzing row for the JVM (jazzer-junit) if the table gains one.
- Konsist against a Gradle wrapper project, to record whether the failure is the layout or
  the version.
