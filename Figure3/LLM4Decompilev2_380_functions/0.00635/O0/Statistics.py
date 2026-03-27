import statistics

'''
Simple script to collect decompiler evaluation statistics.
'''
file_path = "edit_distances.txt"

def collectStatistics():
    line_count = 0

    total_compileable = 0
    total_passes = 0
    total_similarity = 0.0
    total_codebertscore = 0.0
    total_codebleu = 0.0
    total_crystalbleu = 0.0
    total_corpusbleu = 0.0
    total_klee_iCov = 0
    total_klee_bCov = 0
    total_gcov_lineCov = 0
    total_gcov_bCov = 0

    # Lists to calculate medians
    klee_iCov_list = []
    gcov_lineCov_list = []

    # Read the well-formatted edit_distances.txt
    # Format: COMPILEABLE PASS SIMILARITY CODEBERT CODEBLEU CRYSTALBLEU CORPUSBLEU KLEE_ICOV KLEE_BCOV GCOV_LINECOV GCOV_BCOV
    with open(file_path, 'r') as file:
        for line in file:
            line_count += 1
            tokens = line.strip().split()
            if len(tokens) != 11:
                print("Skipping malformed line:", line.strip())
                continue

            compileable, pass_, similarity, codebertscore, codebleu, crystalbleu, corpusbleu, klee_iCov, klee_bCov, gcov_lineCov, gcov_bCov = map(float, tokens)

            if similarity < 0 or similarity > 1:
                print("We skipped because of weird edit distance")
                continue

            total_compileable += int(compileable)
            total_passes += int(pass_)
            total_similarity += similarity
            total_codebertscore += codebertscore
            total_codebleu += codebleu
            total_crystalbleu += crystalbleu
            total_corpusbleu += corpusbleu
            if pass_:
                total_klee_iCov += klee_iCov
                total_klee_bCov += klee_bCov
                total_gcov_lineCov += gcov_lineCov
                total_gcov_bCov += gcov_bCov

            klee_iCov_list.append(klee_iCov)
            gcov_lineCov_list.append(gcov_lineCov)

    # Compute means
    compile_ratio = total_compileable / line_count
    pass_ratio = total_passes / line_count
    average_similarity = total_similarity / line_count
    average_codebertscore = total_codebertscore / line_count
    average_codebleu = total_codebleu / line_count
    average_crystalbleu = total_crystalbleu / line_count
    average_corpusbleu = total_corpusbleu / line_count
    
    average_klee_iCov = total_klee_iCov / total_passes
    average_klee_bCov = total_klee_bCov / total_passes
    average_gcov_lineCov = total_gcov_lineCov / total_passes
    average_gcov_bCov = total_gcov_bCov / total_passes

    # Compute medians
    median_klee_iCov = statistics.median(klee_iCov_list)
    median_gcov_lineCov = statistics.median(gcov_lineCov_list)

    print(f"Number of Tests: {line_count}")
    print(f"Number of Compilations: {total_compileable}")
    print(f"Number of Passes: {total_passes}")
    print(f"Compile Ratio: {compile_ratio:.4f}")
    print(f"Pass Ratio: {pass_ratio:.4f}")
    print(f"Average Similarity: {average_similarity:.4f}")
    print(f"Average CodeBERTScore: {average_codebertscore:.4f}")
    print(f"Average CodeBLEU: {average_codebleu:.4f}")
    print(f"Average CrystalBLEU: {average_crystalbleu:.4f}")
    print(f"Average CorpusBLEU: {average_corpusbleu:.4f}")
    print("\n")
    print(f"Average KLEE Instruction Coverage: {average_klee_iCov:.4f}")
    print(f"Median KLEE Instruction Coverage: {median_klee_iCov:.4f}")
    print("\n")
    print(f"Average GCOV Line Coverage: {average_gcov_lineCov:.4f}")
    print(f"Median GCOV Line Coverage: {median_gcov_lineCov:.4f}")
    print("\n")
    print(f"Average KLEE Branch Coverage: {average_klee_bCov:.4f}")
    print(f"Average GCOV Branch Coverage: {average_gcov_bCov:.4f}")


if __name__ == "__main__":
    collectStatistics()