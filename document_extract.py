import PIL.IcnsImagePlugin
from dotenv import load_dotenv
load_dotenv("C:\\Users\\xiaog\\Desktop\\stuff\\fall24\\urop\\headers.env")
import sys
import google.generativeai as genai
import os
from tqdm import tqdm
import time
import PIL.Image
import fitz  # pip install --upgrade pip; pip install --upgrade pymupdf
from bs4 import BeautifulSoup
import urllib
import requests
import csv
import shutil
import validators
import pdfplumber

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
           'Cookie' : 'aws-waf-token=' + os.environ['AWS_WAF_TOKEN']}
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# media = pathlib.Path(__file__).parents[0] / "francesca-gregorini-v-apple-inc"
calls = ["Find the winner of this case given the following pdfs; if there is no clear winner or final outcome, **tell me the side which is favored** - plantiff or defendant; for whichever side has more possibility of winning, include a statement like 'plaintiff wins' or 'defendant wins'. If initially one side was favored but then rulings were reversed, and that reversal has not been overturned, state the side that was reversed in favor", 
            "Classify the content of this legal document into one of the following categories: \ncase details: Content related to the initial complaint and general context about the case itself. \ncase verdict: Files which contain the verdict of the case, indicating which party (plaintiff or defendant) prevailed. \nother: Any additional content, including court notices, orders, fees, proposed statements, agreements between parties, or summons",
            "Classify this image, which is contained in the following pdf, as belonging to the plaintiff (a.k.a **plantiff image**), the defendant (a.k.a. **defendant image**), or **neither** (irrelevant image). Especially note that some images may be placed next to each other, in which case it is important to differentiate whether the plantiff's image or the defendant's image is on the left or the right. First determine the location of the image in the pdf, then use surrounding captions and context from the pdf to determine this. Each image can only be from either the plantiff or the defendant, not both. "]
text_classifications = ['case details', 'case verdict']
image_classifications = ['plaintiff image', 'defendant image']

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
        return text

def export_pdfs(workdir, pdfs):
    """
    Exports list of uploaded pdfs and their corresponding file names to the Gemini API to a .txt file

    workdir: A working directory to save files
    pdfs: A list where each item in the list is formatted as [Gemini API item, file name]
    """
    with open(os.path.join(workdir, "uploaded_files.txt"), 'w') as f:
        for p in pdfs:
            f.write(p[0] + ', ' + p[1] + '\n')

def import_read_csvs(workdir):
    with open(os.path.join(workdir, "read_csvs.txt"), 'r') as f:
        return [line.strip() for line in f]

def import_read_directories(workdir):
    with open(os.path.join(workdir, "read_directories.txt"), 'r') as f:
        return [line.strip() for line in f]

def upload_pdfs(workdir, local_pdfs=False):
    """
    Uploads all pdfs in a working directory to the Gemini API
    
    TODO: dict instead of list

    workdir: working directory which all pdfs directly stored in workdir are uploaded
    """
    pdfs = []
    for path in tqdm(os.listdir(workdir)):
        if ".pdf" in path:
            if not local_pdfs:
                pdfs.append([genai.upload_file(os.path.join(workdir, path), mime_type="application/pdf").name, path])
            else:
                pdfs.append([extract_text_from_pdf(os.path.join(workdir, path)), path])
            # print(pdfs[-1])

    return pdfs

def import_pdfs(workdir):
    """
    Imports pdf names and their corresponding gemini API file names (as Gemini API can store files up to 48 hours)
    Returns a list where each item has format [gemini API item, pdf name]

    TODO: return as dict instead of list

    workdir: working directory
    """
    if os.path.exists(os.path.join(workdir, "uploaded_files.txt")):
        with open(os.path.join(workdir, "uploaded_files.txt"), 'r') as f:
            return [line.strip().split(', ') for line in f]
    else:
        return []

def delete_all_files(workdir=None):
    """
    Deletes all files which have been uploaded to gemini API to save space
    """
    for x in tqdm(genai.list_files()):
        x.delete()

    if workdir is not None:
        if os.path.exists(os.path.join(workdir, "uploaded_files.txt")):
            os.remove(os.path.join(workdir, "uploaded_files.txt"))

def classify_text(workdir, pdfs, model, local_pdf=False):
    """
    Classify each pdf in a given list as 'case details', 'case verdict', or 'other'. 
    'other' files are extraneous and will not be needed in determining whether or not images are copyright infringement or not

    If gemini runs into some sort of filtering error, files will be labeled as 'try_again' - however, this
    may not work as usually this is due to some sort of NSFW content within the file itself.

    Returns a dictionary of classification -> list of file names
    
    model: the model used for such classification
    pdfs: list of pdfs which need to be classified
    """
    ret = {}
    for val in text_classifications:
        ret[val] = []
    ret["try_again"] = []
    # print(pdfs[0][0])
    for xy in tqdm(pdfs):
        x, pdf_name = xy[0], xy[1]
        # print(xy)
        while True:
            try:
                response = model.generate_content([calls[1], genai.get_file(x) if not local_pdf else x])

                classify = False
                # print(str(x) + ": " + str(response.text))
                for val in text_classifications:
                    if val in response.text:
                        ret[val].append(pdf_name)
                        classify=True

                if not classify:
                    os.remove(os.path.join(workdir, pdf_name))
                break
            except Exception as e:
                if "429" in str(e):
                    time.sleep(60)
                else:
                    print(e)
                    ret["try_again"].append(pdf_name)
                    break
    return ret

def classify_single_pdf(workdir, path, model):
    """
    Classifies a single pdf
    """
    x = genai.upload_file(os.path.join(workdir, path), mime_type="application/pdf")
    while True:
        try:
            response = model.generate_content([calls[1], x])

            for val in text_classifications:
                if val in response.text:
                    return val
            break
        except Exception as e:
            print(e)
            if "429" in str(e):
                time.sleep(60)
            else:
                return "try_again"
    return "other"

def export_text_classifications(workdir, dict):
    """
    Records file classifications in a .txt file

    workdir: working directory
    dict: the dictionary which records the classification of each file
    """
    with open(os.path.join(workdir, "classifications.txt"), 'w') as f:
        for c, arr in dict.items():
            for x in arr:
                f.write(x + ', ' + c + '\n')
    return

def import_text_classifications(workdir):
    """
    Imports file classifications from a .txt file

    workdir: working directory
    """
    ret = {}
    if os.path.exists(os.path.join(workdir, "classifications.txt")):
        with open(os.path.join(workdir, "classifications.txt"), 'r') as f:
            for line in f:
                x = line.rstrip("\n").split(", ")
                if x[1] not in ret:
                    ret[x[1]] = []
                ret[x[1]].append(x[0])
        return ret
    else:
        return {}

def find_winner(pdfs, classifications, model):
    """
    Given a list of relevant pdfs (use only 'case verdict' pdfs) and a model, determine who won the case

    TODO: update this function

    model: model
    classifications: classification of each pdf
    pdfs: list of pdfs
    """
    call = [calls[0]]
    for x in pdfs:
        if x[1] in classifications["case verdict"]:
            call.append(genai.get_file(x[0]))
    response = model.generate_content(call)
    print(response.text)
    if "plaintiff wins" in response.text:
        return "plaintiff"
    else:
        return "defendant"
    
def export_winner(workdir, judgement):
    with open(os.path.join(workdir, "judgement.txt"), 'w') as f:
        f.write(judgement)
    return


def extract_image_from_pdf(workdir, path):
    """
    Extracts all images from a given pdf ( workdir/path(.pdf) ) and saves them in a folder under workdir/path 

    workdir: working directory
    path: folder name
    """
    doc = fitz.Document((os.path.join(workdir, path)))
    newdir = path.rsplit('.', 1)[0]
    os.mkdir(os.path.join(workdir, newdir))
    for i in tqdm(range(len(doc)), desc="pages"):
        for img in tqdm(doc.get_page_images(i), desc="page_images"):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.width < 150 or pix.height < 150:      # eliminate extraneous images; also consider that some are full length screenshots
                continue

            ## TODO: figure out plantiff/defendant and label as such
            pix.save(os.path.join(workdir, newdir, "%s_p%s-%s.png" % (path[:-4], i, xref)))

# IDEA: extract images from pdf, upload images and pdf to api, determine whether each is plantiff or defendants'
def classify_images(workdir, path, pdf, model, extraction_needed=False):
    """
    Given images from a working directory and the pdf they were extracted from, extract images from the pdf path and
    determine whether each image belongs to the plantiff or the defendant

    Note: if try_again is returned (similar to classify_text) it is unlikely the image can be labeled

    Returns a dict of classifications

    workdir: workdir
    path: pdf name
    model: model used for classification
    pdf: corresponding file in the Gemini API
    """
    if extraction_needed:
        extract_image_from_pdf(workdir, path)
    newdir = path.rsplit('.', 1)[0]
    ret = {}
    for val in image_classifications:
        ret[val] = []
    ret["try_again"] = []
    for img in os.listdir(os.path.join(workdir, newdir)):
        opened_img = PIL.Image.open(os.path.join(workdir, newdir, img))
        while True:
            try:
                response = model.generate_content([calls[2], opened_img, genai.get_file(pdf)])

                print(img)
                print(response.text)
                for val in image_classifications:
                    if val in response.text:
                        ret[val].append(img)
                break
            except Exception as e:
                if "429" in str(e):
                    time.sleep(60)
                else:
                    print(e)
                    ret["try_again"].append(img)
                    break
    return ret

def export_image_classifications(workdir, dict):
    with open(os.path.join(workdir, "image_classifications.txt"), 'w') as f:
        for c, arr in dict.items():
            for x in arr:
                f.write(x + ', ' + c + '\n')
    return

def import_image_classifications(workdir):
    ret = {}
    if os.path.exists(os.path.join(workdir, "image_classifications.txt")):
        with open(os.path.join(workdir, "image_classifications.txt"), 'r') as f:
            for line in f:
                x = line.rstrip("\n").split(", ")
                ret[x].append(x[0])
        return ret
    else:
        return {}
    

def extract_img(workdir):
    """
    Extracts all images from all pdfs contained directly in workdir

    workdir: the working directory
    """
    for path in os.listdir(workdir):
        if ".pdf" in path:
            extract_image_from_pdf(workdir, path)
    return


def download_pdf(url, workdir, model=None):
    """
    Downloads the pdf that the URL points to in the working directory

    url: the URL which contains the PDF
    workdir: the working directory the PDF will be downloaded to
    """
    while True:
        try:
            response = urllib.request.urlopen(url)

            test = url.split('/')
            file = open(os.path.join(workdir, test[-1]), 'wb')
            file.write(response.read())
            file.close()

            if model is not None:
                if classify_single_pdf(workdir, test[-1], model) == "other":
                    os.remove(os.path.join(workdir, test[-1]))
            break
        except Exception as e:
            if "429" in str(e):
                time.sleep(60)
            else:
                print(url + " could not be downloaded due to the following error: " + str(e))
                break
    return

# deletes empty folders
def clean(workdir):
    """
    Deletes all empty folders located directly in a working directory

    workdir: working directory
    """
    folders = list(os.walk(workdir))[1:]

    for folder in folders:
        # folder example: ('FOLDER/3', [], ['file'])
        if not folder[2]:
            os.rmdir(folder[0])
    return

# COURTLISTENER ONLY ATM
def extract_from_url(url, workdir, model=None):
    """
    Extracts all pdfs and images within a given **courtlistener** URL.

    TODO:
    - add support for non-courtlistener URLs

    url: URL where pdfs are linked to
    workdir: working directory
    """
    if "courtlistener" in url:
        try:
            pdfs = set()

            original_url = url
            # print(soup)
            while True:
                try:
                    read = requests.get(url, headers=headers)

                    # print(read.status_code)
                    html_content = read.content
                    soup = BeautifulSoup(html_content, "html.parser")
                    v = soup.find('div', id='docket-entry-table')
                    # print(v)

                    for link in v.find_all('a', {}):
                        # print(link.attrs.get('href', 'Not found'))
                        if link.attrs.get('href', 'Not found').find('storage.courtlistener.com') != -1:
                            # print(link.attrs.get('href', 'Not found'))
                            # html_for_pdf = requests.get(url + link.get('href')).content
                            # soup_for_pdf = BeautifulSoup(html_for_pdf, "html.parser")
                            # for tot in soup_for_pdf.find_all('object', type="application/pdf"):
                            #     s = tot.get('data')
                            #     # eh not sure if this works, test later
                            #     if s.find("pdf") != -1:
                            #         pdfs.add(s)
                            pdfs.add(link.attrs.get('href'))
                    # break
                    
                    if not soup.find('a', rel='next'):
                        break
                    elif soup.find('a', rel='next').attrs.get('href') != "#":
                        url = original_url + soup.find('a', rel='next').attrs.get('href')
                    else:
                        break
                except Exception as e:
                    if "429" in str(e):
                        time.sleep(60)
                    else:
                        print(e)
                        break

            print("Parsed!")

            for pdf in tqdm(pdfs):
                download_pdf(pdf, workdir, model)
                # print("Downloaded " + str(cnt) + " out of " + str(len(pdfs)))
        except Exception as e:
            print(url + " || Download failed: " + str(e))
            with open(os.path.join(workdir, "unextracted_files.txt"), 'a') as f:
                f.write(url + '\n')
    else:
        print("Not a courtlistener docket")
        
    return

def extract(url, workdir, model=None, pdf_extract=True, img_extract=True):
    """
    Given a URL, creates the necessary folders/deletes any previous folders with the same name to 
    download pdfs/images from the URL and deletes any folders that are created which do not 
    contain any content.

    url: URL to be parsed
    workdir: working directory
    """
    prv = workdir
    if "courtlistener" not in url:
        print(url + " ERROR: type not supported")
        with open(os.path.join(workdir, "unextracted_urls.txt"), 'a') as f:
            f.write(url + '\n')
        return
    try:
        print("Extracting " + url + "...")
        if not validators.url(url):
            return
        split_url = url.split('/')
        dir_name = (split_url[-1] if split_url[-1] != "" else split_url[-2]) + "\\"

        workdir += "\\" + dir_name
        # print(workdir)
        
        if pdf_extract:
            if os.path.exists(workdir):
                # If the folder exists, delete it
                shutil.rmtree(workdir)
            os.mkdir(workdir)
            print("Directory created")
            extract_from_url(url, workdir, model)
        
        if img_extract:
            extract_img(workdir)
        clean(workdir)
    except Exception as e:
        print(url + " ERROR " + str(e))
        with open(os.path.join(prv, "unextracted_urls.txt"), 'a') as f:
            f.write(url + '\n')

def read_csv(filename, workdir, model=None, pdf_extract=True, img_extract=True):
    """
    Given a .csv file, extracts all images/pdfs from each of the links within the csv within their own folders.

    workdir: working directory
    filename: .csv file
    """
    cnt = 0
    read_csvs = import_read_csvs(workdir)
    f = open(os.path.join(workdir, "read_csvs.txt"), 'a')
    with open(os.path.join(workdir, filename), "r") as file:
        reader = csv.reader(file, delimiter=',')
        print("Currently on || " + workdir + "/" + filename)
        if cnt >= 300:
            f.close()
            return
        for row in reader:
            # print("extracting " + column + "...")
            if row[0] not in read_csvs:
                extract(row[0], workdir, model, pdf_extract, img_extract)
                f.write(row[0] + '\n')
                cnt += 1
    f.close()
    return

def read_all_csvs(workdir):
    """
    Given a working directory, extracts all pdfs and images from links contained within all .csv files.
    """
    filenames = os.listdir(workdir)
    for filename in filenames:
        if filename.endswith(".csv"):
            # numFiles.append(fileNames)
            print("Opening " + filename + "...")
            read_csv(filename, workdir)
    return



def main():    
    model = genai.GenerativeModel("gemini-1.5-flash-001")
    workdir = "C:\\Users\\xiaog\\Desktop\\stuff\\fall24\\urop"
    # read_csv("courtlistener_data.csv", workdir, None, True, False)

    read_directories = import_read_directories(workdir)
    f = open(os.path.join(workdir, "read_directories.txt"), 'a')

    for pth in os.scandir(workdir):
        if pth.is_dir() and pth.name[0].isalpha():
            print("Current Directory: " + pth.name)
            if pth.name in read_directories:
                continue
            
            # delete_all_files()
            cur_workdir = os.path.join(workdir, pth)
            # print(cur_workdir)
            print("Uploading pdfs...")
            pdfs = upload_pdfs(cur_workdir, True)
            # export_pdfs(cur_workdir, pdfs)
            
            print("Classifying text...")
            classified = classify_text(cur_workdir, pdfs, model, True)
            export_text_classifications(cur_workdir, classified)
            # delete_all_files()
            f.write(pth.name + '\n')
    f.close()

    return 0

if __name__ == '__main__':
    sys.exit(main())